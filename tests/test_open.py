from logging import DEBUG
import ffmpegio


def test_fg():
    with ffmpegio.open(
        "color=c=red:d=1:r=10", "rv", f_in="lavfi", pix_fmt="rgb24"
    ) as f:
        I = f.read(-1)
    assert I["shape"][0] == 10


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=DEBUG)
    test_fg()
