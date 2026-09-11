# Nightly automation

CamReview supplies a deterministic `daily` command but no scheduler or long-running daemon.
Schedule one independent process per camera after that camera's recordings for the day are
closed. The command defaults to all footage, all report formats, motion-only processing, no
extraction, and a 30-second file-settle window.

## Operational command

```bash
camreview daily /media/cameras/upstairs --recursive --date yesterday \
  --report-dir /media/reports/upstairs --quiet
```

Report names are deterministic and same-directory atomic writes replace the previous run,
so rerunning a camera-date does not create duplicates. It does recompute the scan. Keep JSON
because it is the checkpoint used for later classification or extraction.

Run the command as an account that can read recordings and create and replace files in the
report directory. For SMB/CIFS, mount or authenticate the share at the operating-system
level before CamReview starts. Use absolute paths in unattended jobs.

## Cron

This example runs at 00:10 local time and scans the previous date:

```cron
10 0 * * * /opt/camreview/.venv/bin/camreview daily /media/cameras/upstairs --recursive --date yesterday --report-dir /media/reports/upstairs --quiet
```

Cron provides a limited environment. Use the virtual environment's absolute executable and
redirect stdout/stderr to the logging destination you monitor if `--quiet` is omitted.

## systemd

Create `/etc/systemd/system/camreview-upstairs.service`:

```ini
[Unit]
Description=Review yesterday's upstairs camera recordings
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=camreview
ExecStart=/opt/camreview/.venv/bin/camreview daily /media/cameras/upstairs --recursive --date yesterday --report-dir /media/reports/upstairs --quiet
```

Create `/etc/systemd/system/camreview-upstairs.timer`:

```ini
[Unit]
Description=Run CamReview nightly for the upstairs camera

[Timer]
OnCalendar=*-*-* 00:10:00
Persistent=true

[Install]
WantedBy=timers.target
```

Then enable it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now camreview-upstairs.timer
systemctl list-timers camreview-upstairs.timer
```

## Windows Task Scheduler

Create a daily task after midnight with:

```text
Program/script: C:\path\to\camera-review\.venv\Scripts\camreview.exe
Arguments: daily D:\Cameras\upstairs --recursive --date yesterday --report-dir D:\Reports\upstairs --quiet
Start in: C:\path\to\camera-review
```

Use a UNC path when the task account does not receive an interactive user's mapped drives.
Store share credentials through Windows rather than in arguments or TOML.

## Separating motion and classification

A small storage server can run motion-only `daily`, then a GPU workstation can classify the
JSON later:

```bash
camreview classify /reports/upstairs_2026-08-12_motion.json \
  --source-root /mounted/cameras/upstairs
```

Preload the model with a short explicit classification before an offline scheduled job.
Bare model names use the local cache described in [Configuration](./configuration.md).

## Monitoring and recovery

Use process exit codes and inspect `run.status` in JSON. Exit `0` can still include non-strict
warnings, so also monitor `issues`, `timeline_gaps`, and `files_skipped`. Exit `130` means an
interrupted scan wrote a report marked `interrupted`. A
`motion_complete_classification_pending` report is safe input to `camreview classify`.

Use `--strict` when any unreadable or malformed input must fail the scheduled job. Without
it, CamReview favors a usable partial report with explicit gaps. See
[Troubleshooting](./troubleshooting.md) for all exit codes.
