import pytest

from imagegen.options import build_parser, parse_args
from imagegen.registry import MODEL_REGISTRY

pytestmark = pytest.mark.usefixtures("test_env_file")


def test_image_size_must_be_allowed():
    parser = build_parser(MODEL_REGISTRY)
    # pick an invalid size
    with pytest.raises(SystemExit):
        parse_args(
            ["schnell", "-p", "x", "-i", "not_a_size"],
            registry=MODEL_REGISTRY,
            parser=parser,
        )
    # allowed example should pass
    allowed_sizes = MODEL_REGISTRY["schnell"]["options"]["image_size"]["allowed_sizes"]
    ok_size = next(iter(allowed_sizes))
    ns = parse_args(
        ["schnell", "-p", "x", "-i", ok_size], registry=MODEL_REGISTRY, parser=parser
    )
    assert ns.params["image_size"] == ok_size


def test_image_size_accepts_dimensions_for_whi():
    parser = build_parser(MODEL_REGISTRY)
    ns = parse_args(
        ["dev", "-p", "x", "-w", "1024", "-h", "768"],
        registry=MODEL_REGISTRY,
        parser=parser,
    )
    assert ns.params["image_size"] == {"width": 1024, "height": 768}
    with pytest.raises(SystemExit):
        parse_args(
            ["dev", "-p", "x", "-i", "1024x768"],
            registry=MODEL_REGISTRY,
            parser=parser,
        )


def test_width_height_disallowed_for_model():
    parser = build_parser(MODEL_REGISTRY)
    # realism does not allow width/height; providing them should error
    with pytest.raises(SystemExit):
        parse_args(
            ["realism", "-p", "x", "-w", "800", "-h", "600"],
            registry=MODEL_REGISTRY,
            parser=parser,
        )


def test_nano_banana_maps_aspect_ratio():
    parser = build_parser(MODEL_REGISTRY)
    ns = parse_args(
        ["nano-banana", "-p", "x", "-i", "16:9"],
        registry=MODEL_REGISTRY,
        parser=parser,
    )
    assert "image_size" not in ns.params
    assert ns.params["aspect_ratio"] == "16:9"
