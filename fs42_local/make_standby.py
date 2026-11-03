# T-ManTV standby splash: python3 make_standby.py <out.png> [black|navy]
import os, sys
from PIL import Image, ImageDraw, ImageFont
OUT = sys.argv[1]; CARD = sys.argv[2] if len(sys.argv) > 2 else "black"
FD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
W, H = 720, 480
img = Image.new("RGB", (W, H)); d = ImageDraw.Draw(img)
top = [(192,192,192),(192,192,0),(0,192,192),(0,192,0),(192,0,192),(192,0,0),(0,0,192)]
mid = [(0,0,192),(19,19,19),(192,0,192),(19,19,19),(0,192,192),(19,19,19),(192,192,192)]
bw = W / 7; h1, h2 = int(H*0.67), int(H*0.75)
for i in range(7):
    x0, x1 = round(i*bw), round((i+1)*bw)
    d.rectangle([x0,0,x1,h1], fill=top[i]); d.rectangle([x0,h1,x1,h2], fill=mid[i])
x = 0.0
for c, m in [((0,33,76),1.25),((255,255,255),1.25),((50,0,106),1.25),((19,19,19),1.25),
             ((9,9,9),1/3),((19,19,19),1/3),((29,29,29),1/3),((19,19,19),1)]:
    d.rectangle([round(x),h2,round(x+m*bw),H], fill=c); x += m*bw
d.rectangle([round(x),h2,W,H], fill=(19,19,19))
cw, ch = 490, 230; cx0, cy0 = (W-cw)//2, int(H*0.40)-ch//2
card = [cx0, cy0, cx0+cw, cy0+ch]
d.rounded_rectangle([c+8 for c in card], 18, fill=(0,0,0))
d.rounded_rectangle(card, 18, fill=(10,16,60) if CARD == "navy" else (5,5,5), outline=(255,255,255), width=5)
d.rounded_rectangle([card[0]+11,card[1]+11,card[2]-11,card[3]-11], 12, outline=(255,210,0), width=2)
def mask(text, font, y):
    m = Image.new("L", (W, H), 0); md = ImageDraw.Draw(m)
    b = md.textbbox((0,0), text, font=font)
    md.text(((W-(b[2]-b[0]))//2-b[0], y-b[1]), text, font=font, fill=255)
    return m, b[3]-b[1]
ly = cy0 + 38
lm, lh = mask("T-ManTV", ImageFont.truetype(os.path.join(FD, "BungeeShade-Regular.ttf"), 72), ly)
grad = Image.new("RGB", (W, H)); gd = ImageDraw.Draw(grad)
for yy in range(H):
    t = min(max((yy-ly)/lh, 0), 1)
    gd.line([(0,yy),(W,yy)], fill=(255, int(214-94*t), 0))
img.paste(grad, (0,0), lm)
d = ImageDraw.Draw(img)
d.line([cx0+60, cy0+142, cx0+cw-60, cy0+142], fill=(255,210,0), width=3)
sm, _ = mask("PLEASE STAND BY", ImageFont.truetype(os.path.join(FD, "PressStart2P-Regular.ttf"), 20), cy0+165)
img.paste(Image.new("RGB", (W,H), (120,255,120)), (0,0), sm)
img.save(OUT); print("saved", OUT, "(" + CARD + " card)")
