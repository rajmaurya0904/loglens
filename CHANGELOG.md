# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0] - YYYY-MM-DD
### Added
- Aggregate logs from multiple services (docker compose, k8s) in real-time
- Colorize logs per service for easy visual distinction
- Merge logs in chronological order using a priority queue
- Timestamp each log line with UTC timestamp at receipt
- Resilience to source termination (container restart, pod reschedule)
- CLI interface with options to filter services and limit lines