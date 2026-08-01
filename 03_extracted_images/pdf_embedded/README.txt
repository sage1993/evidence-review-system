law-1 / law-2 PDF image extraction package

Folders for each document:
1. 01_raw_embedded_streams
   - Direct extraction with Poppler pdfimages.
   - Includes raster images, image masks, and soft-mask streams.
   - This is the broadest definition of embedded image streams.

2. 02_visible_unique_images
   - One PNG per unique PDF image XObject (xref), with soft masks composited where possible.
   - Repeated placement of the same xref is stored once here.

3. 03_visible_occurrence_crops
   - Every resolvable image placement cropped from the rendered PDF page at 200 DPI.
   - Preserves the image as it appears on the page and includes repeated occurrences.

4. 04_pages_containing_images
   - Full-page 150 DPI renders for pages that contain embedded image objects.
   - Useful for checking image location and surrounding labels.

Manifest CSV files contain page numbers, PDF object IDs/xrefs, dimensions, bounding boxes, hashes, and file names.

Important limitation:
PDF vector lines, shapes, text, and diagrams built from drawing commands are not embedded raster images. They will not appear as separate files in image-object extraction. They remain visible in the full-page renders. To turn a vector diagram or a mixed table/diagram into one image, crop that region from the page render separately.
