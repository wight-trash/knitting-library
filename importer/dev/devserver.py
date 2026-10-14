"""Run the importer against a pretend DROPS and a pretend Knitting Library, for looking at the screens.
Set SHARE_TOKEN to try POST /api/share."""
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx, uvicorn
from app.config import Settings
from app.drops.fetcher import DropsFetcher
from app.kl.client import KnittingLibrary
from app.main import create_app
from tests.conftest import drops_handler
from tests.fakekl import FakeKL

mode = os.environ.get("DROPS_MODE", "ok")
s = Settings(kl_url="http://kl.test", kl_public_url="https://knit.example", kl_password="pw",
             data_dir=Path(tempfile.mkdtemp()), drops_min_interval=float(os.environ.get("INTERVAL", "0.8")),
             chromium_path=os.environ.get("CHROMIUM_PATH", "/usr/bin/chromium"),
             share_token=os.environ.get("SHARE_TOKEN", ""))
kl = FakeKL(duplicate=bool(os.environ.get("DUP")))
app = create_app(s, fetcher=DropsFetcher(s, transport=httpx.MockTransport(drops_handler(mode))),
                 kl=KnittingLibrary(s, transport=kl.transport()))
uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8099")), log_level="warning")
