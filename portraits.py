"""
四位投資人的素描風格頭像（SVG）。是依外型特徵畫的插畫，不是照片或寫實肖像。
鉛筆質感：feTurbulence + feDisplacementMap 讓線條微微抖動，再疊一層淡淡的交叉排線當陰影。
執行：python portraits.py → static/portraits/{id}.svg
"""
from pathlib import Path

OUT = Path(__file__).parent / "static" / "portraits"

DEFS = """<defs>
  <filter id="pencil" x="-5%" y="-5%" width="110%" height="110%">
    <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="{seed}" result="n"/>
    <feDisplacementMap in="SourceGraphic" in2="n" scale="2.2" xChannelSelector="R" yChannelSelector="G"/>
  </filter>
  <pattern id="hatch" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(35)">
    <line x1="0" y1="0" x2="0" y2="5" stroke="#3a3f47" stroke-width="0.7" opacity="0.55"/>
  </pattern>
  <pattern id="hatch2" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(-40)">
    <line x1="0" y1="0" x2="0" y2="4" stroke="#3a3f47" stroke-width="0.6" opacity="0.5"/>
  </pattern>
  <pattern id="hair" width="3" height="3" patternUnits="userSpaceOnUse" patternTransform="rotate(60)">
    <line x1="0" y1="0" x2="0" y2="3" stroke="#22252b" stroke-width="1.3" opacity="0.85"/>
  </pattern>
</defs>"""

STROKE = 'fill="none" stroke="#2b2f36" stroke-linecap="round" stroke-linejoin="round"'


def svg(seed: int, bg: str, body: str) -> str:
    import re
    # 有排線填色的形狀，拿掉共用樣式裡的 fill="none"，避免重複屬性
    body = re.sub(r'(<[^>]*fill="url\(#(?:hatch2?|hair)\)"[^>]*?) fill="none"', r"\1", body)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 240" role="img">'
            f'{DEFS.format(seed=seed)}<rect width="200" height="240" fill="{bg}"/>'
            f'<g filter="url(#pencil)">{body}</g></svg>')


# 共用：西裝領口與領帶
SUIT = f'''<path d="M30 240 C40 205 62 192 84 186 L100 214 L116 186 C138 192 160 205 170 240" {STROKE} stroke-width="2"/>
<path d="M84 186 L92 240 M116 186 L108 240" {STROKE} stroke-width="1.4"/>
<path d="M93 196 L100 214 L107 196 L103 192 L97 192 Z" fill="url(#hatch2)" {STROKE} stroke-width="1.3"/>
<path d="M97 214 L94 240 M103 214 L106 240" {STROKE} stroke-width="1.2"/>'''

BUFFETT = svg(3, "#eef4ec", f'''
<!-- 臉型：下顎較寬、臉頰飽滿 -->
<path d="M60 92 C58 130 66 160 84 176 C94 184 106 184 116 176 C134 160 142 130 140 92" {STROKE} stroke-width="2.2"/>
<path d="M62 120 C64 150 76 168 92 176" fill="url(#hatch)" stroke="none" opacity=".5"/>
<!-- 白髮：往後梳、兩側蓬鬆有波浪 -->
<path d="M58 100 C50 70 62 42 92 36 C118 31 142 44 146 70 C148 82 145 94 141 100" {STROKE} stroke-width="2.2"/>
<path d="M62 78 C72 58 90 50 108 52 M70 66 C84 50 108 46 128 56 M112 54 C126 58 136 68 140 82" {STROKE} stroke-width="1.2" opacity=".8"/>
<path d="M56 96 C50 104 52 112 58 116 M144 96 C150 104 148 112 142 116" {STROKE} stroke-width="1.6"/>
<!-- 耳朵 -->
<path d="M60 104 C52 102 50 118 58 124 M140 104 C148 102 150 118 142 124" {STROKE} stroke-width="1.8"/>
<!-- 濃眉 -->
<path d="M70 94 C78 88 88 88 94 92 M106 92 C112 88 122 88 130 94" {STROKE} stroke-width="3"/>
<!-- 眼鏡：圓角方框 -->
<rect x="68" y="98" width="28" height="20" rx="7" {STROKE} stroke-width="2"/>
<rect x="104" y="98" width="28" height="20" rx="7" {STROKE} stroke-width="2"/>
<path d="M96 106 C99 104 101 104 104 106 M68 104 L60 102 M132 104 L140 102" {STROKE} stroke-width="1.6"/>
<path d="M76 109 C79 106 85 106 88 109 M112 109 C115 106 121 106 124 109" {STROKE} stroke-width="1.6"/>
<!-- 鼻子 -->
<path d="M100 112 C98 124 94 134 96 138 C99 141 104 140 106 137" {STROKE} stroke-width="1.6"/>
<!-- 招牌笑容與法令紋 -->
<path d="M82 150 C92 160 108 160 118 150" {STROKE} stroke-width="2"/>
<path d="M86 152 C94 156 106 156 114 152" {STROKE} stroke-width="1.1"/>
<path d="M80 134 C76 142 77 150 82 154 M120 134 C124 142 123 150 118 154" {STROKE} stroke-width="1.3" opacity=".8"/>
{SUIT}''')

MUNGER = svg(7, "#f6efe3", f'''
<!-- 臉型：長、下垂的臉頰與雙下巴 -->
<path d="M64 88 C60 128 66 158 80 172 C90 182 110 182 120 172 C134 158 140 128 136 88" {STROKE} stroke-width="2.2"/>
<path d="M82 172 C90 184 110 184 118 172" {STROKE} stroke-width="1.4"/>
<path d="M66 118 C68 146 76 162 88 170" fill="url(#hatch)" stroke="none" opacity=".55"/>
<!-- 禿頂與兩側短髮 -->
<path d="M64 92 C60 58 76 34 100 32 C124 34 140 58 136 92" {STROKE} stroke-width="2.2"/>
<path d="M60 82 L64 74 M58 90 L63 84 M60 98 L64 92 M140 82 L136 74 M142 90 L137 84 M140 98 L136 92" {STROKE} stroke-width="1.6"/>
<path d="M80 50 C92 44 108 44 120 50" {STROKE} stroke-width=".9" opacity=".5"/>
<!-- 耳朵 -->
<path d="M64 100 C55 98 54 116 62 122 M136 100 C145 98 146 116 138 122" {STROKE} stroke-width="1.8"/>
<!-- 招牌粗框大眼鏡 -->
<rect x="66" y="94" width="31" height="25" rx="5" fill="none" stroke="#1d2026" stroke-width="5"/>
<rect x="103" y="94" width="31" height="25" rx="5" fill="none" stroke="#1d2026" stroke-width="5"/>
<path d="M97 103 L103 103 M66 100 L60 98 M134 100 L140 98" stroke="#1d2026" stroke-width="4" stroke-linecap="round"/>
<path d="M75 107 L88 107 M112 107 L125 107" {STROKE} stroke-width="1.8"/>
<path d="M72 90 L90 88 M110 88 L128 90" {STROKE} stroke-width="2.4"/>
<!-- 鼻子 -->
<path d="M100 118 C98 130 95 138 97 142 C100 145 105 144 107 141" {STROKE} stroke-width="1.6"/>
<!-- 嘴角微微下垂、表情嚴肅 -->
<path d="M84 156 C92 153 108 153 116 156" {STROKE} stroke-width="2"/>
<path d="M80 140 C76 150 78 158 84 162 M120 140 C124 150 122 158 116 162" {STROKE} stroke-width="1.3" opacity=".8"/>
{SUIT}''')

DUAN = svg(11, "#e9eff8", f'''
<!-- 臉型：圓潤 -->
<path d="M62 96 C60 132 70 160 88 172 C96 178 104 178 112 172 C130 160 140 132 138 96" {STROKE} stroke-width="2.2"/>
<path d="M64 122 C66 146 76 162 90 170" fill="url(#hatch)" stroke="none" opacity=".45"/>
<!-- 黑色短髮、旁分 -->
<path d="M60 98 C54 62 74 40 102 40 C128 40 146 60 140 98 C136 82 130 72 118 66 C104 72 82 72 68 80 C64 86 62 92 60 98 Z" fill="url(#hair)" {STROKE} stroke-width="2"/>
<path d="M118 66 C110 58 98 54 84 56" {STROKE} stroke-width="1.6"/>
<path d="M70 64 C84 52 104 48 124 54" {STROKE} stroke-width="1.2"/>
<!-- 耳朵 -->
<path d="M62 106 C54 104 53 120 60 126 M138 106 C146 104 147 120 140 126" {STROKE} stroke-width="1.8"/>
<!-- 眉毛與笑眼 -->
<path d="M72 96 C79 92 87 92 92 95 M108 95 C113 92 121 92 128 96" {STROKE} stroke-width="2.4"/>
<path d="M74 108 C79 104 85 104 90 108 M110 108 C115 104 121 104 126 108" {STROKE} stroke-width="2"/>
<!-- 鼻子 -->
<path d="M100 112 C98 122 95 130 97 134 C100 136 104 136 106 133" {STROKE} stroke-width="1.6"/>
<!-- 溫和的笑 -->
<path d="M84 148 C92 156 108 156 116 148" {STROKE} stroke-width="2"/>
<!-- POLO 衫領 -->
<path d="M36 240 C44 206 64 192 86 186 L100 200 L114 186 C136 192 156 206 164 240" {STROKE} stroke-width="2"/>
<path d="M86 186 L80 204 L100 200 L120 204 L114 186" {STROKE} stroke-width="1.6"/>
<path d="M100 200 L100 222 M100 208 L101 208 M100 216 L101 216" {STROKE} stroke-width="1.6"/>''')

LILU = svg(17, "#f1ecf7", f'''
<!-- 臉型：橢圓、較瘦 -->
<path d="M64 92 C62 130 70 158 86 172 C95 179 105 179 114 172 C130 158 138 130 136 92" {STROKE} stroke-width="2.2"/>
<path d="M66 120 C68 146 78 162 90 170" fill="url(#hatch)" stroke="none" opacity=".45"/>
<!-- 短髮、額頭略高 -->
<path d="M62 96 C56 62 74 38 100 38 C126 38 144 62 138 96 C136 84 132 76 126 70 C116 64 102 62 88 64 C78 66 70 72 66 82 C64 86 63 90 62 96 Z" fill="url(#hair)" {STROKE} stroke-width="2"/>
<path d="M76 66 C88 58 110 56 126 66" {STROKE} stroke-width="1.2"/>
<!-- 耳朵 -->
<path d="M64 102 C56 100 55 116 62 122 M136 102 C144 100 145 116 138 122" {STROKE} stroke-width="1.8"/>
<!-- 細框眼鏡（橢圓、無框感） -->
<ellipse cx="83" cy="106" rx="13" ry="9.5" {STROKE} stroke-width="1.3"/>
<ellipse cx="117" cy="106" rx="13" ry="9.5" {STROKE} stroke-width="1.3"/>
<path d="M96 105 C98 103 102 103 104 105 M70 104 L64 102 M130 104 L136 102" {STROKE} stroke-width="1.2"/>
<path d="M72 92 C78 89 86 89 92 92 M108 92 C114 89 122 89 128 92" {STROKE} stroke-width="2.2"/>
<circle cx="83" cy="107" r="2.2" fill="#2b2f36"/><circle cx="117" cy="107" r="2.2" fill="#2b2f36"/>
<!-- 鼻子 -->
<path d="M100 114 C98 124 96 132 98 136 C100 138 104 138 106 135" {STROKE} stroke-width="1.6"/>
<!-- 沉穩的淺笑 -->
<path d="M86 150 C94 155 106 155 114 150" {STROKE} stroke-width="1.9"/>
<!-- 西裝、開領襯衫不打領帶 -->
<path d="M30 240 C40 205 62 192 84 186 L100 210 L116 186 C138 192 160 205 170 240" {STROKE} stroke-width="2"/>
<path d="M84 186 L92 240 M116 186 L108 240 M100 210 L100 240" {STROKE} stroke-width="1.4"/>''')

PORTRAITS = {"duan": DUAN, "buffett": BUFFETT, "munger": MUNGER, "lilu": LILU}

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for key, s in PORTRAITS.items():
        (OUT / f"{key}.svg").write_text(s, encoding="utf-8")
    print("✅", ", ".join(PORTRAITS))
