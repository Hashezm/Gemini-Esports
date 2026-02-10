"""
Fast multi-template tracker using OpenCV matchTemplate + mss.

Changes vs your version:
- Removes pyautogui.locate() and PIL templates from the hot path
- Uses OpenCV matchTemplate on numpy arrays (much faster)
- One screenshot per frame shared across all templates
- Per-template ROI heuristic (search around last_pos), fallback to full-frame
- Optional thread pool (OpenCV often releases the GIL, so threads can help)

Notes:
- Confidence threshold is applied to matchTemplate score (TM_CCOEFF_NORMED by default)
- If you want multiple detections per template, you’d do thresholding + NMS; this finds best match.
"""

from __future__ import annotations

import os
import time
import glob
from dataclasses import dataclass
from typing import List, Optional, Tuple, Union, Dict
from concurrent.futures import ThreadPoolExecutor

import cv2 as cv
import numpy as np
import mss


@dataclass
class MatchResult:
    id: int
    found: bool
    x: int
    y: int
    w: int
    h: int
    score: float
    method: str  # "Heuristic" or "Full Scan" or "Not Found"


@dataclass
class TemplateState:
    id: int
    path: str
    tpl: np.ndarray          # BGR template
    tpl_gray: np.ndarray     # grayscale template
    tpl_small: np.ndarray    # downscaled template (BGR or gray based on setting)
    w: int
    h: int
    w_small: int             # downscaled width
    h_small: int             # downscaled height
    last_pos: Optional[Tuple[int, int]] = None
    found: bool = False


class MultiTemplateTrackerCV:
    def __init__(
        self,
        template_paths: Union[str, List[str]],
        confidence: float = 0.85,
        search_margin: int = 150,
        max_workers: int = 0,
        method: int = cv.TM_CCOEFF_NORMED,
        use_grayscale: bool = True,
        downscale_factor: float = 0.5,  # NEW: downscale for faster matching
        skip_full_scan: bool = True,    # Skip full-res fallback when pyramid enabled
    ):
        if isinstance(template_paths, str):
            template_paths = [template_paths]

        self.confidence = float(confidence)
        self.search_margin = int(search_margin)
        self.method = method
        self.use_grayscale = use_grayscale
        self.downscale_factor = float(downscale_factor)
        self.use_pyramid = downscale_factor < 1.0
        self.skip_full_scan = skip_full_scan and self.use_pyramid  # Only skip if pyramid is on

        self.sct = mss.mss()
        self.monitor = self.sct.monitors[1]
        self.screen_w = int(self.monitor["width"])
        self.screen_h = int(self.monitor["height"])
        
        # Pre-compute downscaled screen dimensions
        self.screen_w_small = int(self.screen_w * self.downscale_factor)
        self.screen_h_small = int(self.screen_h * self.downscale_factor)

        self.templates: List[TemplateState] = []
        for i, path in enumerate(template_paths):
            tpl = cv.imread(path, cv.IMREAD_COLOR)
            if tpl is None:
                raise FileNotFoundError(f"Failed to load template: {path}")
            h, w = tpl.shape[:2]
            tpl_gray = cv.cvtColor(tpl, cv.COLOR_BGR2GRAY)
            
            # Pre-compute downscaled template
            w_small = max(1, int(w * self.downscale_factor))
            h_small = max(1, int(h * self.downscale_factor))
            if self.use_grayscale:
                tpl_small = cv.resize(tpl_gray, (w_small, h_small), interpolation=cv.INTER_AREA)
            else:
                tpl_small = cv.resize(tpl, (w_small, h_small), interpolation=cv.INTER_AREA)
            
            self.templates.append(
                TemplateState(
                    id=i, path=path, tpl=tpl, tpl_gray=tpl_gray, tpl_small=tpl_small,
                    w=w, h=h, w_small=w_small, h_small=h_small
                )
            )
            print(f"[T{i}] Loaded: {path} ({w}x{h}) -> small: ({w_small}x{h_small})")

        self.executor: Optional[ThreadPoolExecutor] = None
        self.max_workers = int(max_workers)
        if self.max_workers and self.max_workers > 0:
            self.executor = ThreadPoolExecutor(max_workers=self.max_workers)

        print(f"[MultiTemplateTrackerCV] Total templates: {len(self.templates)}")
        print(f"[MultiTemplateTrackerCV] Confidence: {self.confidence}")
        print(f"[MultiTemplateTrackerCV] ROI margin: {self.search_margin}")
        print(f"[MultiTemplateTrackerCV] Threads: {self.max_workers if self.executor else 0}")
        print(f"[MultiTemplateTrackerCV] Grayscale: {self.use_grayscale}")
        print(f"[MultiTemplateTrackerCV] Method: {self.method}")
        print(f"[MultiTemplateTrackerCV] Downscale: {self.downscale_factor} ({'pyramid' if self.use_pyramid else 'disabled'})")
        print(f"[MultiTemplateTrackerCV] Skip full scan: {self.skip_full_scan}")

    def shutdown(self):
        if self.executor:
            self.executor.shutdown(wait=False)

    def _grab_frame_bgr(self) -> np.ndarray:
        """Grab full screen as BGR numpy array."""
        sct_img = self.sct.grab(self.monitor)          # BGRA
        frame = np.asarray(sct_img, dtype=np.uint8)    # HxWx4
        frame_bgr = cv.cvtColor(frame, cv.COLOR_BGRA2BGR)
        return frame_bgr

    def _best_match(
        self,
        frame: np.ndarray,
        tpl: np.ndarray,
        method: int,
    ) -> Tuple[float, int, int]:
        """
        Return (best_score, best_x, best_y) for matchTemplate.
        For TM_SQDIFF* lower is better; for others higher is better.
        """
        res = cv.matchTemplate(frame, tpl, method)
        min_val, max_val, min_loc, max_loc = cv.minMaxLoc(res)
        if method in (cv.TM_SQDIFF, cv.TM_SQDIFF_NORMED):
            # lower is better: convert to "score where higher is better"
            score = 1.0 - float(min_val)
            x, y = min_loc
        else:
            score = float(max_val)
            x, y = max_loc
        return score, int(x), int(y)

    def _match_one(self, t: TemplateState, frame_bgr: np.ndarray, frame_gray: Optional[np.ndarray],
                   frame_small: Optional[np.ndarray] = None) -> MatchResult:
        w, h = t.w, t.h

        # pick channel representation for full-res matching
        if self.use_grayscale:
            frame = frame_gray
            tpl = t.tpl_gray
        else:
            frame = frame_bgr
            tpl = t.tpl

        assert frame is not None

        # Heuristic ROI first (uses full resolution)
        if t.last_pos is not None:
            lx, ly = t.last_pos
            roi_x = max(0, lx - self.search_margin)
            roi_y = max(0, ly - self.search_margin)
            roi_w = min(self.search_margin * 2 + w, self.screen_w - roi_x)
            roi_h = min(self.search_margin * 2 + h, self.screen_h - roi_y)

            # Need ROI >= template size
            if roi_w >= w and roi_h >= h:
                roi = frame[roi_y : roi_y + roi_h, roi_x : roi_x + roi_w]
                score, x, y = self._best_match(roi, tpl, self.method)
                if score >= self.confidence:
                    return MatchResult(
                        id=t.id, found=True,
                        x=roi_x + x, y=roi_y + y,
                        w=w, h=h,
                        score=score,
                        method="Heuristic",
                    )

        # PYRAMID MATCHING: search at low resolution first, then refine
        if self.use_pyramid and frame_small is not None:
            # Step 1: Match at low resolution
            if frame_small.shape[1] >= t.w_small and frame_small.shape[0] >= t.h_small:
                score_small, x_small, y_small = self._best_match(frame_small, t.tpl_small, self.method)
                
                # Lower threshold for coarse search (we'll verify at full res)
                if score_small >= self.confidence * 0.9:
                    # Step 2: Scale coordinates back to full resolution
                    scale = 1.0 / self.downscale_factor
                    x_full = int(x_small * scale)
                    y_full = int(y_small * scale)
                    
                    # Step 3: Refine in a small ROI at full resolution
                    refine_margin = max(20, int(50 / self.downscale_factor))
                    roi_x = max(0, x_full - refine_margin)
                    roi_y = max(0, y_full - refine_margin)
                    roi_w = min(w + refine_margin * 2, self.screen_w - roi_x)
                    roi_h = min(h + refine_margin * 2, self.screen_h - roi_y)
                    
                    if roi_w >= w and roi_h >= h:
                        roi = frame[roi_y : roi_y + roi_h, roi_x : roi_x + roi_w]
                        score, x, y = self._best_match(roi, tpl, self.method)
                        if score >= self.confidence:
                            return MatchResult(
                                id=t.id, found=True,
                                x=roi_x + x, y=roi_y + y,
                                w=w, h=h,
                                score=score,
                                method="Pyramid",
                            )

        # Full scan fallback (only if pyramid disabled or skip_full_scan is False)
        if not self.skip_full_scan:
            if frame.shape[1] >= w and frame.shape[0] >= h:
                score, x, y = self._best_match(frame, tpl, self.method)
                if score >= self.confidence:
                    return MatchResult(
                        id=t.id, found=True,
                        x=x, y=y,
                        w=w, h=h,
                        score=score,
                        method="Full Scan",
                    )

        return MatchResult(
            id=t.id, found=False,
            x=0, y=0,
            w=w, h=h,
            score=0.0,
            method="Not Found",
        )

    def find_all(self) -> List[MatchResult]:
        frame_bgr = self._grab_frame_bgr()
        self._last_frame = frame_bgr  # Cache for get_preview_frame()
        
        frame_gray = cv.cvtColor(frame_bgr, cv.COLOR_BGR2GRAY) if self.use_grayscale else None
        
        # Create downscaled frame for pyramid matching
        # Use INTER_NEAREST for speed (less accurate but much faster than INTER_AREA)
        frame_small = None
        if self.use_pyramid:
            if self.use_grayscale:
                frame_small = cv.resize(frame_gray, (self.screen_w_small, self.screen_h_small), 
                                        interpolation=cv.INTER_NEAREST)
            else:
                frame_small = cv.resize(frame_bgr, (self.screen_w_small, self.screen_h_small), 
                                        interpolation=cv.INTER_NEAREST)

        if self.executor:
            futures = [self.executor.submit(self._match_one, t, frame_bgr, frame_gray, frame_small) 
                      for t in self.templates]
            results = [f.result() for f in futures]
        else:
            results = [self._match_one(t, frame_bgr, frame_gray, frame_small) for t in self.templates]

        # Update per-template state
        for r in results:
            t = self.templates[r.id]
            if r.found:
                t.last_pos = (r.x, r.y)
                t.found = True
            else:
                t.last_pos = None
                t.found = False

        return results

    def get_preview_frame(self) -> np.ndarray:
        """Return cached frame from last find_all() - no extra screen grab."""
        if hasattr(self, '_last_frame') and self._last_frame is not None:
            return self._last_frame
        return self._grab_frame_bgr()


def run_tracking_loop_cv(
    template_paths: Union[str, List[str]],
    confidence: float = 0.85,
    search_margin: int = 150,
    show_preview: bool = True,
    max_workers: int = 0,
    use_grayscale: bool = True,
    target_fps: int = 60,
    downscale_factor: float = 0.5,  # NEW: pyramid matching scale
    skip_full_scan: bool = True,    # Skip full-res fallback when pyramid enabled
):
    tracker = MultiTemplateTrackerCV(
        template_paths=template_paths,
        confidence=confidence,
        search_margin=search_margin,
        max_workers=max_workers,
        use_grayscale=use_grayscale,
        method=cv.TM_CCOEFF_NORMED,
        downscale_factor=downscale_factor,
        skip_full_scan=skip_full_scan,
    )

    colors = [
        (0, 255, 0),
        (255, 0, 0),
        (0, 0, 255),
        (255, 255, 0),
        (255, 0, 255),
        (0, 255, 255),
    ]

    frame_count = 0
    start_time = time.time()

    stats: Dict[int, Dict[str, int]] = {i: {"heuristic": 0, "full": 0, "pyramid": 0, "found": 0} for i in range(len(tracker.templates))}

    try:
        while True:
            loop_start = time.time()

            results = tracker.find_all()
            frame_count += 1
            elapsed = time.time() - start_time
            actual_fps = frame_count / elapsed if elapsed > 0 else 0.0

            found_any = False
            for r in results:
                if r.found:
                    found_any = True
                    stats[r.id]["found"] += 1
                    if r.method == "Heuristic":
                        stats[r.id]["heuristic"] += 1
                    elif r.method == "Pyramid":
                        stats[r.id]["pyramid"] += 1
                    elif r.method == "Full Scan":
                        stats[r.id]["full"] += 1

            # log (light)
            if found_any:
                found_str = ", ".join([f"T{r.id}@({r.x},{r.y}) s={r.score:.2f} {r.method}" for r in results if r.found])
                print(f"Frame {frame_count} (FPS: {actual_fps:.1f}): {found_str}")
            else:
                # print about once per second
                if actual_fps > 0 and frame_count % max(1, int(actual_fps)) == 0:
                    print(f"Frame {frame_count} (FPS: {actual_fps:.1f}): None found")

            if show_preview:
                frame = tracker.get_preview_frame()
                for r in results:
                    if r.found:
                        c = colors[r.id % len(colors)]
                        cv.rectangle(frame, (r.x, r.y), (r.x + r.w, r.y + r.h), c, 2)
                        cv.putText(frame, f"T{r.id} {r.score:.2f}", (r.x, max(15, r.y - 8)),
                                   cv.FONT_HERSHEY_SIMPLEX, 0.5, c, 2)

                cv.putText(frame, f"FPS: {actual_fps:.1f}", (10, 25), cv.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                found_count = sum(1 for r in results if r.found)
                cv.putText(frame, f"Found: {found_count}/{len(results)}", (10, 55), cv.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

                preview = cv.resize(frame, (1280, 720))
                cv.imshow("MultiTemplateTrackerCV", preview)
                if cv.waitKey(1) & 0xFF == ord("q"):
                    break

            # crude FPS cap (optional)
            if target_fps > 0:
                budget = 1.0 / float(target_fps)
                spent = time.time() - loop_start
                if spent < budget:
                    time.sleep(budget - spent)

    except KeyboardInterrupt:
        print("\nInterrupted")
    finally:
        tracker.shutdown()
        if show_preview:
            cv.destroyAllWindows()

        total_time = time.time() - start_time
        print("\n" + "=" * 50)
        print("Performance Summary")
        print("=" * 50)
        print(f"Total frames: {frame_count}")
        print(f"Average FPS: {frame_count / total_time:.1f}" if total_time > 0 else "Average FPS: n/a")
        print()
        for tid, s in stats.items():
            total = s["found"]
            pct = 100.0 * total / max(1, frame_count)
            h_pct = 100.0 * s["heuristic"] / max(1, total) if total > 0 else 0.0
            p_pct = 100.0 * s["pyramid"] / max(1, total) if total > 0 else 0.0
            print(f"T{tid}: Found {total} ({pct:.1f}%), Heuristic: {h_pct:.1f}%, Pyramid: {p_pct:.1f}%")


if __name__ == "__main__":
    import sys

    # Default extraction dir: relative to this file's location
    EXTRACTION_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "game_agent", "extraction_stuff")

    confidence = 0.90
    if len(sys.argv) > 1:
        if "," in sys.argv[1]:
            templates = [t.strip() for t in sys.argv[1].split(",")]
        else:
            # all args except last (if numeric) are templates
            if len(sys.argv) > 2 and sys.argv[-1].replace(".", "", 1).isdigit():
                templates = sys.argv[1:-1]
                confidence = float(sys.argv[-1])
            else:
                templates = sys.argv[1:]
    else:
        templates = glob.glob(os.path.join(EXTRACTION_DIR, "*", "reference_crop.png"))
        if not templates:
            print(f"No reference_crop.png files found in {EXTRACTION_DIR}/*/")
            print("Run your extraction pipeline first.")
            raise SystemExit(1)

        print(f"Auto-discovered {len(templates)} reference crops:")
        for t in templates:
            enemy_name = os.path.basename(os.path.dirname(t))
            print(f"  - {enemy_name}: {t}")

    # threads: start with 0 (single-thread). If you have many templates, try 4 or 8.
    max_workers = min(8, len(templates)) if len(templates) >= 6 else 0

    print(f"\nTemplates: {len(templates)}")
    print(f"Confidence: {confidence}")
    print(f"Max workers: {max_workers}")

    run_tracking_loop_cv(
        templates,
        confidence=confidence,
        search_margin=150,
        show_preview=True,
        max_workers=max_workers,
        use_grayscale=True,
        target_fps=60,
        downscale_factor=0.5,
        skip_full_scan=True,
    )
