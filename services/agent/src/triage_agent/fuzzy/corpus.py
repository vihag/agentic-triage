"""Seed corpus: past incidents, known patterns, and benign baselines.

Summaries are short and non-procedural. A few of them reuse the ids cited by
the triage-decision examples (INC-2041, BASE-03, BASE-12) and the words those
alerts actually contain, so kNN can rank them.
"""

from __future__ import annotations

from dataclasses import dataclass

from triage_agent.contract import Severity


@dataclass(frozen=True)
class CorpusItem:
    ref_id: str
    ref_type: str
    summary: str
    verified_severity: Severity
    verdict: str


def _incident(
    ref_id: str, summary: str, severity: Severity, verdict: str = "true_positive"
) -> CorpusItem:
    return CorpusItem(ref_id, "past_incident", summary, severity, verdict)


def _pattern(ref_id: str, summary: str, severity: Severity, verdict: str = "unknown") -> CorpusItem:
    return CorpusItem(ref_id, "known_pattern", summary, severity, verdict)


def _baseline(
    ref_id: str, summary: str, severity: Severity, verdict: str = "benign_true_positive"
) -> CorpusItem:
    return CorpusItem(ref_id, "benign_baseline", summary, severity, verdict)


CORPUS: tuple[CorpusItem, ...] = (
    _incident(
        "INC-2041",
        "Excessive failed logins followed by success. Credential stuffing against VPN, "
        "one account compromised.",
        "high",
    ),
    _incident(
        "INC-1888",
        "Impossible travel sign-in to Office 365 from a new country after a VPN failure.",
        "high",
    ),
    _incident(
        "INC-1760",
        "Privileged user added to domain admins outside the change window.",
        "critical",
    ),
    _incident(
        "INC-990",
        "TOR egress from a finance workstation to an external exit node.",
        "high",
    ),
    _incident(
        "INC-1502",
        "Malware execution on a laptop after a user opened a phishing attachment.",
        "high",
    ),
    _incident(
        "INC-1420",
        "Phishing attachment delivered a remote access tool. Mailbox rules were changed.",
        "medium",
    ),
    _incident(
        "INC-1301",
        "Bulk download of customer files followed by an upload to a personal cloud drive.",
        "high",
    ),
    _incident(
        "INC-1211",
        "SSH password spray against bastion hosts. One key was copied off the host.",
        "high",
    ),
    _incident(
        "INC-1104",
        "Ransomware note appeared on a file server after shadow copies were deleted.",
        "critical",
    ),
    _incident(
        "INC-1044",
        "Insider searched the HR export and copied it to removable media.",
        "high",
    ),
    _incident(
        "INC-980",
        "A new cloud admin key was created and used from an unseen network.",
        "high",
    ),
    _incident(
        "INC-870",
        "DNS tunneling from a point-of-sale host to an unregistered domain.",
        "medium",
    ),
    _pattern(
        "PAT-01",
        "Known pattern: excessive failed logins followed by one success from a hosting provider.",
        "high",
    ),
    _pattern(
        "PAT-02",
        "Known pattern: password spray across many accounts from one external address.",
        "medium",
    ),
    _pattern(
        "PAT-03",
        "Known pattern: EICAR test file on a CI build agent during the nightly self-test.",
        "informational",
        "benign_true_positive",
    ),
    _pattern(
        "PAT-04",
        "Known pattern: outbound connection to a TOR exit node.",
        "high",
    ),
    _pattern(
        "PAT-05",
        "Known pattern: noisy external port scan with no successful session.",
        "low",
        "false_positive",
    ),
    _pattern(
        "PAT-06",
        "Known pattern: vulnerability scanner source address hitting many ports.",
        "low",
        "false_positive",
    ),
    _pattern(
        "PAT-07",
        "Known pattern: forged Kerberos ticket used against a domain controller.",
        "critical",
    ),
    _pattern(
        "PAT-08",
        "Known pattern: impossible travel between two interactive sign-ins.",
        "high",
    ),
    _pattern(
        "PAT-09",
        "Known pattern: encoded PowerShell launched by a macro document.",
        "high",
    ),
    _pattern(
        "PAT-10",
        "Known pattern: newly consented OAuth application reading mail.",
        "high",
    ),
    _pattern(
        "PAT-11",
        "Known pattern: service account used for an interactive workstation logon.",
        "medium",
    ),
    _pattern(
        "PAT-12",
        "Known pattern: domain controller login outside the patch window.",
        "high",
    ),
    _baseline(
        "BASE-03",
        "Nightly AV self-test on CI agents. EICAR test file on the build agent.",
        "informational",
    ),
    _baseline(
        "BASE-12",
        "User forgot password after a reset. A few failed logins then one success "
        "from a corporate device.",
        "low",
    ),
    _baseline(
        "BASE-04",
        "CI build agent malware signature during the scheduled scanner self-test.",
        "informational",
    ),
    _baseline(
        "BASE-05",
        "Known corporate vulnerability scanner sweeping the lab network.",
        "low",
        "false_positive",
    ),
    _baseline(
        "BASE-06",
        "Backup service account reads file shares on its nightly schedule.",
        "low",
    ),
    _baseline(
        "BASE-07",
        "Patch window reboot of domain workstations. Expected shutdown events.",
        "low",
    ),
    _baseline(
        "BASE-08",
        "Mail gateway quarantined a marketing newsletter. No user click.",
        "informational",
    ),
    _baseline(
        "BASE-09",
        "Developer workstation installed packages from the internal registry.",
        "low",
    ),
    _baseline(
        "BASE-10",
        "Employee on a published trip signed in from the conference network.",
        "low",
    ),
    _baseline(
        "BASE-11",
        "Scheduled vulnerability scan from the scanner allow-list.",
        "low",
        "false_positive",
    ),
    _baseline(
        "BASE-13",
        "Service desk password reset for a caller who failed the first quiz.",
        "low",
    ),
    _baseline(
        "BASE-14",
        "Malware lab detonated the EICAR test file on an isolated host.",
        "informational",
    ),
)
