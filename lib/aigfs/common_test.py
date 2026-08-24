from aigfs import common


def test_common_platforms():
    assert common.platforms() == ["ursa", "wcoss2"]
