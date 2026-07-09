# Fingerprint Surface Model

Chromium-family anti-detect work must treat fingerprinting as a consistency system, not as independent string replacement.

## Surface inventory

| Surface | Runtime-owned behavior | Required evidence |
| --- | --- | --- |
| Seed identity | Stable deterministic identity from `fingerprint_seed`. | Repeated launches produce stable values where intended. |
| User agent | Version/OS/browser family coherence. | Detector UA/client-hints consistency. |
| Client hints | `Sec-CH-UA*`, platform, architecture, bitness, mobile. | BrowserLeaks/client hints output. |
| Timezone | Direct/proxy-aware timezone. | JS timezone + IP geography coherence. |
| Locale | Accept-Language, navigator language(s), UI locale. | Header + JS consistency. |
| Screen/window | Screen size, avail size, DPR, outer/inner metrics. | BrowserLeaks/Pixelscan screen checks. |
| Hardware | hardwareConcurrency, deviceMemory, platform hints. | Detector consistency and plausible ranges. |
| Canvas | Stable, plausible canvas output/noise. | BrowserLeaks/CreepJS canvas hashes. |
| WebGL | Vendor, renderer, params, extensions, shader precision, pixel output. | All-or-nothing WebGL profile evidence. |
| Audio | Stable AudioContext output/noise. | BrowserScan/BrowserLeaks audio checks. |
| Fonts | Font list and metrics coherent with target OS. | Pixelscan font mismatch checks. |
| WebRTC | Local/public IP leak policy and proxy coherence. | BrowserLeaks WebRTC results. |
| Storage quota | Persistent context should not look incognito unless intentionally configured. | BrowserScan incognito/storage deductions. |
| Permissions/features | Browser feature inventory should match claimed browser version. | CreepJS missing API checks. |
| Automation | CDP/WebDriver/headless signals. | SannySoft/CreepJS automation checks. |

## WebGL rule

Incomplete WebGL spoofing is worse than no override. A release cannot claim WebGL support unless it proves coherence across strings, extension count/list hash, parameters, shader precision formats, and rendered pixel output for the target platform/GPU model.

## Evidence states

| State | Meaning |
| --- | --- |
| `not_tested` | Surface is known but no evidence exists. Release blocker for high-risk surfaces. |
| `warn` | Detector found inconsistency or evidence is incomplete. Requires mitigation or accepted risk. |
| `pass` | Detector evidence supports current implementation for the tested environment. |
| `accepted_risk` | Known risk is documented with rationale and release owner approval. |

## Release blocker rule

High/critical surfaces cannot ship with `not_tested` or unaccepted `warn/fail` findings.
