import pdfplumber

from collections import defaultdict, deque

pdf_path = "main.pdf"

def obj_to_bbox(obj):
    return [obj["x0"], obj["top"], obj["x1"], obj["bottom"]]

def get_lines_rects_curves(page):

    print(f"Total lines: {len(page.lines)}, Total rects: {len(page.rects)}, Total curves: {len(page.curves)}")

    line_boxes = [obj_to_bbox(l) for l in page.lines]
    rect_boxes = [obj_to_bbox(r) for r in page.rects]
    curve_boxes = [obj_to_bbox(c) for c in page.curves]

    return line_boxes + rect_boxes + curve_boxes

def visualise_and_output_bboxes(page, bounding_boxes, filename="debug.png"):

    im = page.to_image(resolution=150)
    im.draw_rects(bounding_boxes, stroke="red", stroke_width=2)
    im.save(filename)

def iou(a, b):
    # Unpack box coordinates
    xa1, ya1, xa2, ya2 = a
    xb1, yb1, xb2, yb2 = b

    # Compute intersection rectangle
    ix1 = max(xa1, xb1)  # left edge
    iy1 = max(ya1, yb1)  # bottom edge
    ix2 = min(xa2, xb2)  # right edge
    iy2 = min(ya2, yb2)  # top edge

    # Intersection width and height (>= 0)
    iw = max(0, ix2 - ix1)
    ih = max(0, iy2 - iy1)

    # Area of intersection
    inter = iw * ih

    # Area of each box
    area_a = (xa2 - xa1) * (ya2 - ya1)
    area_b = (xb2 - xb1) * (yb2 - yb1)

    # Union = sum - intersection
    union = area_a + area_b - inter

    # Avoid division by zero
    return inter / union if union > 0 else 0.0


def box_height(b):
    # Height = top - bottom
    return b[3] - b[1]

def horizontal_gap(a, b):
    # If boxes overlap horizontally → gap = 0
    # Otherwise gap = distance between edges
    return max(0, max(a[0], b[0]) - min(a[2], b[2]))

def vertical_overlap_ratio(a, b):
    # Compute vertical overlap length
    overlap = max(0, min(a[3], b[3]) - max(a[1], b[1]))

    # Normalize by the smaller box height
    min_h = min(box_height(a), box_height(b))

    # Return overlap as a fraction of height
    return overlap / min_h if min_h > 0 else 0.0

def should_merge(
    a,
    b,
    iou_thresh,
    gap_ratio,
    vert_overlap_thresh,
):
    # If boxes overlap enough, they belong together

    if iou(a, b) >= iou_thresh:
        return True
    
    # Find the smaller box height
    min_h = min(box_height(a), box_height(b))

    # Invalid boxes safeguard
    if min_h <= 0:
        return False
    # If boxes are:
    # - close horizontally
    # - well aligned vertically
    if (
        horizontal_gap(a, b) <= gap_ratio * min_h
        and vertical_overlap_ratio(a, b) >= vert_overlap_thresh
    ):
        return True
    
    # Otherwise: do not merge
    return False

def hybrid_group_boxes(
    boxes,
    iou_thresh=0.1,
    gap_ratio=1.0,
    vert_overlap_thresh=0.5,
):
    n = len(boxes)
    graph = defaultdict(list)

    # Build edges
    for i in range(n):
        for j in range(i + 1, n):
            if should_merge(
                boxes[i],
                boxes[j],
                iou_thresh,
                gap_ratio,
                vert_overlap_thresh,
            ):
                graph[i].append(j)
                graph[j].append(i)

    # Connected components
    visited = [False] * n
    groups = []

    for i in range(n):
        if visited[i]:
            continue

        queue = deque([i])
        visited[i] = True
        group = [i]

        while queue:
            u = queue.popleft()
            for v in graph[u]:
                if not visited[v]:
                    visited[v] = True
                    queue.append(v)
                    group.append(v)

        groups.append(group)

    return groups

def merge_groups(boxes, groups):
    merged = []

    for group in groups:
        x0 = min(boxes[i][0] for i in group)
        y0 = min(boxes[i][1] for i in group)
        x1 = max(boxes[i][2] for i in group)
        y1 = max(boxes[i][3] for i in group)

        merged.append([x0, y0, x1, y1])

    return merged


def get_image_bboxes(page):
    boxes = []

    for img in page.images:
        if "bbox" in img:
            boxes.append(list(img["bbox"]))
        else:
            boxes.append([img["x0"], img["top"], img["x1"], img["bottom"]])

    return boxes


with pdfplumber.open(pdf_path) as pdf:
    page = pdf.pages[19]  # first page

    image_bboxes = get_image_bboxes(page)
    visualise_and_output_bboxes(page, image_bboxes, "image_bboxes_debug.png")

    initial_bboxes = get_lines_rects_curves(page)
    visualise_and_output_bboxes(page, initial_bboxes)

    groups = hybrid_group_boxes(
        initial_bboxes,
        iou_thresh=0.01,
        gap_ratio=0.5,
        vert_overlap_thresh=1.0,
    )

    merged_boxes = merge_groups(initial_bboxes, groups)
    visualise_and_output_bboxes(page, merged_boxes, "merged_boxes.png")

