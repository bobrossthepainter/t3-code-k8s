import pathlib
import subprocess
import unittest

import yaml

CHART = "charts/t3-code"


def render(*args, fail=False):
    result = subprocess.run(
        ["helm", "template", "test", CHART, "--set", "image.repository=ghcr.io/example/t3-code-k8s", *args],
        capture_output=True, text=True,
    )
    if fail:
        if result.returncode == 0:
            raise AssertionError("Expected invalid values to be rejected")
        return result.stderr
    if result.returncode:
        raise AssertionError(result.stderr)
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def kind(docs, name):
    return next(doc for doc in docs if doc["kind"] == name)


class ChartTests(unittest.TestCase):
    def test_lint(self):
        subprocess.run(["helm", "lint", "--strict", CHART, "--set", "image.repository=ghcr.io/example/t3-code-k8s"], check=True)

    def test_defaults(self):
        docs = render()
        deployment = kind(docs, "Deployment")
        self.assertEqual(deployment["spec"]["replicas"], 1)
        self.assertEqual(deployment["spec"]["strategy"]["type"], "Recreate")
        pod = deployment["spec"]["template"]["spec"]
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertEqual(pod["securityContext"]["fsGroup"], 10001)
        self.assertTrue(pod["containers"][0]["securityContext"]["readOnlyRootFilesystem"])
        self.assertEqual(pod["volumes"][0]["persistentVolumeClaim"]["claimName"], kind(docs, "PersistentVolumeClaim")["metadata"]["name"])
        self.assertNotIn("storageClassName", kind(docs, "PersistentVolumeClaim")["spec"])
        self.assertFalse(any(doc["kind"] == "Ingress" for doc in docs))

    def test_storage_modes(self):
        docs = render("--set", "persistence.enabled=false")
        self.assertFalse(any(doc["kind"] == "PersistentVolumeClaim" for doc in docs))
        self.assertIn("emptyDir", kind(docs, "Deployment")["spec"]["template"]["spec"]["volumes"][0])
        docs = render("--set", "persistence.existingClaim=existing")
        self.assertFalse(any(doc["kind"] == "PersistentVolumeClaim" for doc in docs))
        self.assertEqual(kind(docs, "Deployment")["spec"]["template"]["spec"]["volumes"][0]["persistentVolumeClaim"]["claimName"], "existing")
        self.assertEqual(kind(render("--set", "persistence.storageClass="), "PersistentVolumeClaim")["spec"]["storageClassName"], "")

    def test_ingress_modes(self):
        docs = render("--set", "ingress.enabled=true", "--set", "ingress.className=nginx")
        self.assertEqual(kind(docs, "Ingress")["spec"]["ingressClassName"], "nginx")
        docs = render("--set", "tailscale.enabled=true")
        ingress = kind(docs, "Ingress")
        self.assertEqual(ingress["spec"]["ingressClassName"], "tailscale")
        self.assertIn("defaultBackend", ingress["spec"])
        self.assertEqual(ingress["spec"]["tls"][0]["hosts"], ["t3-code"])
        render("--set", "tailscale.enabled=true", "--set", "ingress.enabled=true", fail=True)

    def test_digest_and_network_policy(self):
        digest = "sha256:" + "a" * 64
        docs = render("--set", f"image.digest={digest}", "--set", "networkPolicy.enabled=true")
        image = kind(docs, "Deployment")["spec"]["template"]["spec"]["containers"][0]["image"]
        self.assertEqual(image, f"ghcr.io/example/t3-code-k8s@{digest}")
        self.assertEqual(kind(docs, "NetworkPolicy")["spec"]["ingress"], [])

    def test_examples(self):
        for path in pathlib.Path("examples").glob("*.yaml"):
            with self.subTest(path=path):
                render("-f", str(path))

    def test_invalid_values(self):
        render("--set", "server.port=70000", fail=True)
        render("--set", "image.digest=not-a-digest", fail=True)
        render("--set", "service.type=invalid", fail=True)


if __name__ == "__main__":
    unittest.main()
