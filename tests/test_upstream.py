import importlib.util
import io
import unittest
import urllib.error
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("upstream", "scripts/upstream.py")
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)


def release(version, prerelease=False, **extra):
    return {"tag_name": f"v{version}", "prerelease": prerelease, "draft": False,
            "published_at": "2026-10-30T00:00:00Z", **extra}


class UpstreamTests(unittest.TestCase):
    def test_channel_filter(self):
        for version, pre, stable, nightly in [
            ("0.1.5", False, True, False),
            ("0.1.6-nightly.20261030.3940", True, False, True),
            ("0.1.6-preview.20261030.3948", True, False, False),
            ("0.1.6-alpha.1", True, False, False),
            ("0.1.5", True, False, False),
            ("0.1.6-nightly.20261030.3940", False, False, False),
            ("../../bad", False, False, False),
        ]:
            with self.subTest(version=version, prerelease=pre):
                self.assertEqual(u.valid_release(release(version, pre), "stable"), stable)
                self.assertEqual(u.valid_release(release(version, pre), "nightly"), nightly)
        self.assertFalse(u.valid_release(release("0.1.5", draft=True), "stable"))

    @patch.object(u, "api")
    def test_nightly_excludes_preview_and_selects_latest_published(self, api):
        older = release("0.1.6-nightly.1", True, published_at="2026-10-28T00:00:00Z")
        newer = release("0.1.6-nightly.2", True)
        api.return_value = [release("0.1.6-preview.3", True), older, newer]
        self.assertEqual(u.select_release("nightly"), newer)

    @patch.object(u, "api")
    def test_exact_version_cannot_cross_channels(self, api):
        api.return_value = release("0.1.5")
        with self.assertRaises(ValueError):
            u.select_release("nightly", "0.1.5")
        with self.assertRaises(ValueError):
            u.select_release("stable", "0.1.5; echo pwned")

    @patch.object(u, "api")
    def test_only_404_means_unpublished(self, api):
        for code in (401, 403, 429, 500):
            api.side_effect = urllib.error.HTTPError("url", code, "error", {}, io.BytesIO())
            self.addCleanup(api.side_effect.close)
            with self.assertRaises(urllib.error.HTTPError):
                u.published("owner/repo", "stable", "0.1.5")
        api.side_effect = urllib.error.HTTPError("url", 404, "not found", {}, io.BytesIO())
        self.addCleanup(api.side_effect.close)
        self.assertFalse(u.published("owner/repo", "stable", "0.1.5"))
        api.side_effect = None
        api.return_value = {"draft": True}
        self.assertFalse(u.published("owner/repo", "stable", "0.1.5"))
        api.return_value = {"draft": False}
        self.assertTrue(u.published("owner/repo", "stable", "0.1.5"))

    def test_repository_validation(self):
        with self.assertRaises(ValueError):
            u.published("owner/repo?bad", "stable", "0.1.5")

    @patch.object(u, "request")
    def test_both_assets_must_have_unambiguous_checksums(self, request):
        prefix = f"https://github.com/{u.UPSTREAM}/releases/download/v0.1.5/"
        r = release("0.1.5", assets=[{"name": name, "browser_download_url": prefix + name}
                    for name in ("SHA256SUMS", "t3-0.1.5-linux-x64.tar.gz", "t3-0.1.5-linux-arm64.tar.gz")])
        sums = "a" * 64 + "  t3-0.1.5-linux-x64.tar.gz\n" + "b" * 64 + " *t3-0.1.5-linux-arm64.tar.gz\n"
        request.return_value = sums.encode()
        self.assertEqual(u.checksums(r), {"sha256_amd64": "a" * 64, "sha256_arm64": "b" * 64})
        for invalid in (sums.splitlines()[0], sums + sums, sums.replace("a" * 64, "nope")):
            request.return_value = invalid.encode()
            with self.assertRaises(ValueError):
                u.checksums(r)
        r["assets"][0]["browser_download_url"] = "https://evil.example/SHA256SUMS"
        with self.assertRaises(ValueError):
            u.checksums(r)


if __name__ == "__main__":
    unittest.main()
