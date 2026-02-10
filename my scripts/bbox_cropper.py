from PIL import Image, ImageDraw
import os

def crop_and_save_bbox(image_path, min_x, max_x, min_y, max_y, output_path):
    """
    Crops a localized area from an image based on bounding box coordinates and saves it.

    Args:
        image_path (str): The file path to the source image.
        min_x (int): The minimum x-coordinate (left edge of the box).
        max_x (int): The maximum x-coordinate (right edge of the box).
        min_y (int): The minimum y-coordinate (top edge of the box).
        max_y (int): The maximum y-coordinate (bottom edge of the box).
        output_path (str): The file path where the cropped image will be saved.
    """
    try:
        # Open the image file
        with Image.open(image_path) as img:
            # PIL's crop method expects a tuple: (left, top, right, bottom)
            # Ensure coordinates are integers
            box = (int(min_x), int(min_y), int(max_x), int(max_y))
            ninja_box_perfect = [924, 616, 946, 693]
            img_perfect = Image.open(image_path)
            draw_perfect = ImageDraw.Draw(img_perfect)
            draw_perfect.rectangle(ninja_box_perfect, outline='red', width=1)
            img_perfect.save('final_output.png')
            # Crop the image
            cropped_img = img.crop(box)
            
            # Save the cropped image
            cropped_img.save(output_path)
            print(f"Successfully saved cropped image to: {output_path}")
            return output_path
            
    except FileNotFoundError:
        print(f"Error: The file {image_path} was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    # Example usage if run directly
    crop_and_save_bbox("videos/Desktop Screenshot 2026.02.07 - 10.51.35.12.png", 924, 946, 616, 693, "cropped_ninja.png")
"""
- **Min X:** 923
- **Max X:** 949
- **Min Y:** 598
- **Max Y:** 645 
542, 912, 624, 952 [ymin, xmin, ymax, xmax]
[924, 616, 946, 693] # [xmin, ymin, xmax, ymax]
"""