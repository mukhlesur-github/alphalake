import pytest

from alphalake.common.config import get_settings


@pytest.fixture(scope="session")
def generated(tmp_path_factory):
    """Run the real generators once into a temp data dir."""
    d = tmp_path_factory.mktemp("data")
    mp = pytest.MonkeyPatch()
    mp.setenv("DATA_DIR", str(d))
    get_settings.cache_clear()
    from alphalake.docs.pipeline import parse_all
    from alphalake.generators.documents import generate_documents
    from alphalake.generators.run import generate
    generate()
    generate_documents()
    parse_all()
    yield d
    mp.undo()
    get_settings.cache_clear()
