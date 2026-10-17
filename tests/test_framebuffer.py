import random

from PIL import Image, ImageDraw

from g13d.lcd import framebuffer as fb


def _random_image(seed):
    rnd = random.Random(seed)
    img = Image.new("1", (fb.WIDTH, fb.HEIGHT), 0)
    px = img.load()
    for _ in range(2000):
        px[rnd.randrange(fb.WIDTH), rnd.randrange(fb.HEIGHT)] = 1
    return img


def test_report_shape():
    data = fb.encode(fb.new_image())
    assert len(data) == fb.REPORT_SIZE == 992
    assert data[0] == 0x03
    assert not any(data[1:])


def test_single_pixels():
    for x, y in ((0, 0), (159, 42), (37, 9), (100, 40)):
        img = fb.new_image()
        img.putpixel((x, y), 1)
        data = fb.encode(img)
        idx = 32 + x + (y // 8) * 160
        assert data[idx] == 1 << (y % 8)
        assert sum(data[1:]) == data[idx]


def test_fast_matches_reference():
    for seed in range(5):
        img = _random_image(seed)
        assert fb.encode(img) == fb.encode_slow(img)


def test_text_roundtrip_nonempty():
    img = fb.new_image()
    ImageDraw.Draw(img).text((2, 2), "g13d", fill=1)
    assert any(fb.encode(img)[32:])
