import hashlib
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from app.evaluation.contracts import DETECTION_THRESHOLD, EvaluationMetadata
from app.services.alerts import ALERT_POLICY_VERSION, ALERT_THRESHOLD
from app.services.deterministic_analysis import DETERMINISTIC_POLICY_VERSION
from app.services.hybrid_scoring import HYBRID_POLICY_VERSION
from app.services.semantic_analysis import SEMANTIC_PROMPT_VERSION

ROOT = Path(__file__).resolve().parents[3]
DETECTOR_FILES = (
    "app/services/deterministic_analysis.py",
    "app/services/domain_similarity.py",
    "app/services/semantic_analysis.py",
    "app/services/hybrid_scoring.py",
    "app/schemas/analysis.py",
    "app/services/alerts.py",
    "app/services/email_analysis.py",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze_metadata(mode: str, dataset: Path, context: Path) -> EvaluationMetadata:
    protected = [str(ROOT / "backend" / name) for name in DETECTOR_FILES]
    protected.extend([str(dataset.resolve()), str(context.resolve())])
    # A reproducible freeze cannot silently include uncommitted detector/data edits.
    subprocess.run(
        ["git", "diff", "--exit-code", "HEAD", "--", *protected],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    return EvaluationMetadata(
        mode=mode,
        generated_at=datetime.now(UTC),
        git_commit=commit,
        dataset_sha256=sha256(dataset),
        context_sha256=sha256(context),
        policies={
            "deterministic": DETERMINISTIC_POLICY_VERSION,
            "semantic": SEMANTIC_PROMPT_VERSION,
            "hybrid": HYBRID_POLICY_VERSION,
            "alert": ALERT_POLICY_VERSION,
        },
        thresholds={"detection": DETECTION_THRESHOLD, "alert": ALERT_THRESHOLD},
        detector_sha256={name: sha256(ROOT / "backend" / name) for name in DETECTOR_FILES},
    )
