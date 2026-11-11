from datetime import datetime,timezone
from hashlib import file_digest
import json
from pathlib import Path

OUT=Path(__file__).parent
ROOT=Path('D:/codex_projects/youtube')
VIDEO=ROOT/'output/four-base-counting-001-v002-to-200/paspla-studio-four-ways-to-count-0-to-200-1080p.mp4'
def read(path):return json.loads(path.read_text(encoding='utf-8'))
def digest(path):
    with path.open('rb') as f:return file_digest(f,'sha256').hexdigest()
visual=read(OUT/'four-base-final-qa.json')
technical=read(OUT/'technical-qa.json')
additional=read(OUT/'additional/additional-visual-checks.json')
cells=read(OUT/'additional/per-symbol-cells.json')
assert visual['status']==technical['status']==additional['status']==cells['status']=='pass'
assert technical['sha256']==visual['video_sha256']==additional['video_sha256']==digest(VIDEO)
reading=visual['visual']['native_layout']['reading_probes']
report={
    'status':'pass','checked_at_utc':datetime.now(timezone.utc).isoformat(),
    'video':str(VIDEO),'video_sha256':digest(VIDEO),
    'technical':technical['measurements'],
    'standard_sampled_frames':visual['visual']['sampled_frames'],
    'standard_planned_frames':visual['visual']['planned_samples'],
    'standard_visual_errors':visual['visual']['errors'],
    'native_numeric_row_probes':sum(len(x['rows']) for x in reading),
    'minimum_native_whole_row_glyph_iou':min(y['glyph_iou'] for x in reading for y in x['rows']),
    'minimum_subtitle_iou':min(x['subtitle_iou'] for x in reading),
    'minimum_bird_iou':min(x['glyph_mask_iou'] for x in visual['visual']['native_layout']['bird_probes']),
    'whole_video_presence_fields':additional['numeric_presence_fields'],
    'unexpected_empty_fields':len(additional['unexpected_empty_numeric_fields']),
    'black_frames':len(additional['black_frames']),
    'individual_symbol_cells':cells['cells'],'individual_nonblank_cells':cells['nonblank_cells'],
    'minimum_individual_symbol_iou':cells['minimum_nonblank_cell_iou'],
    'wrong_bit_guard_rejected':cells['guard']['rejected'],
    'assistant_image_inspection':{
        'method':'view_image: two contact sheets plus full native frames 008 (128) and 023 (200).',
        'observations':[
            'All four representations switch together at 127→128, 159→160, 191→192 and 199→200, with no intermediate mixed-value frame in the five-frame boundary neighborhoods.',
            'Binary eight-place fields, octal 200/240/300/310, hexadecimal 80/A0/C0/C8 and decimal 128/160/192/200 are correct.',
            'Range subtitle reads 0–200 IN DECIMAL. Label blocks and number baselines align; no clipping or unintended text collision is visible.',
            'The final 200 stays visible through its spoken highlight and the closing hold, then the image fades to the intended cream endpoint.',
            'Wing, near-ground peck and small hop retain a consistent small bird body/contour, visible panel separation and a stable contact shadow.',
        ],
        'no_new_media_defect_found':True,
        'limits':'This is assistant image review of extracted frames and complete automated decode/scans, not a claim that a human watched every frame.',
    },
    'evidence':[
        'technical-qa.json','four-base-final-qa.json','additional/additional-visual-checks.json',
        'additional/per-symbol-cells.json','additional/boundaries-contact-sheet.png',
        'additional/finale-motion-contact-sheet.png',
    ],
}
(OUT/'visual-audit-summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({key:report[key] for key in ['status','standard_sampled_frames','native_numeric_row_probes','minimum_native_whole_row_glyph_iou','minimum_individual_symbol_iou','whole_video_presence_fields','black_frames','unexpected_empty_fields']}))
