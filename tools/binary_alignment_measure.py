"""Measure visible typography and marker groups from rendered RGB pixels."""
from __future__ import annotations

from PIL import Image, ImageChops, ImageStat


def typography_mask(image):
    """Keep dark warm, purple and teal glyphs; exclude cream and pale outlines."""
    red,green,blue=image.convert('RGB').split()
    masks=(red.point(lambda value:255 if value<180 else 0),
           green.point(lambda value:255 if value<155 else 0),
           blue.point(lambda value:255 if value<155 else 0))
    result=masks[0]
    for mask in masks[1:]:result=ImageChops.multiply(result,mask)
    return result


def marker_mask(image):
    """Keep the pale carry markers and teal active marker, not their board."""
    red,green,blue=image.convert('RGB').split()
    tests=(red.point(lambda value:255 if value<240 else 0),
           green.point(lambda value:255 if value<232 else 0),
           blue.point(lambda value:255 if value<220 else 0))
    return ImageChops.multiply(ImageChops.multiply(tests[0],tests[1]),tests[2])


def bbox_report(mask, crop, content_box, name):
    box=mask.getbbox()
    if not box:raise ValueError(f'No visible ink in {name}')
    absolute=[box[0]+crop[0],box[1]+crop[1],box[2]+crop[0],box[3]+crop[1]]
    center=(absolute[1]+absolute[3])/2
    target=(content_box[1]+content_box[3])/2
    return {'name':name,'ink_bbox':absolute,'ink_center_y':center,'content_box':list(content_box),
            'target_center_y':target,'vertical_center_delta_px':round(center-target,3)}


def measure_main_alignment(image, origin=(0,0)):
    """Measure the main lower group from a full frame or its decoded board crop."""
    content=(658,622,1802,798)
    crop=(674,632,1785,790)
    local=(crop[0]-origin[0],crop[1]-origin[1],crop[2]-origin[0],crop[3]-origin[1])
    return bbox_report(typography_mask(image.crop(local)),crop,content,'decimal-and-say-group')


def measure_alignment(frame, include_carry=False, carry_top=823, carry_bottom=893):
    """Measure three red-circled groups without consulting renderer text origins."""
    reports=[]
    reports.append(measure_main_alignment(frame))
    if include_carry:
        content=(670,carry_top,1790,carry_bottom)
        crop=(685,carry_top+4,1775,carry_bottom-4)
        image=frame.crop(crop)
        mask=typography_mask(image)
        # Inactive carry markers are pale, so their pixels need their own mask.
        # Restrict to their small horizontal band to avoid decorative board ink.
        markers=Image.new('L',image.size,0)
        region=(300, max(0,carry_bottom-28-crop[1]), 800, carry_bottom-5-crop[1])
        markers.paste(marker_mask(image.crop(region)),region[:2])
        reports.append(bbox_report(ImageChops.lighter(mask,markers),crop,content,'carry-title-and-markers'))
    width=(1772-18*6)/7
    for index in range(7):
        x=74+index*(width+18)
        content=(x,935,x+width,1046)
        crop=(round(x+16),947,round(x+width-16),1037)
        reports.append(bbox_report(typography_mask(frame.crop(crop)),crop,content,f'range-card-{index+1}'))
    return reports
