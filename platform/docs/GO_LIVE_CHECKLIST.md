# Go-Live Checklist

**Project:** Unified Solar Performance Platform  
**Target Date:** _______________  
**Sign-off By:** _______________

---

## Security

- [ ] Default admin password changed from any defaults
- [ ] All API keys stored in environment variables (not in code or config files)
- [ ] HTTPS/TLS enabled for production URL
- [ ] Session timeout configured (max 30 minutes idle)
- [ ] Rate limiting enabled on API endpoints
- [ ] Audit logging enabled — all login/logout and admin actions recorded
- [ ] `.env` file excluded from version control (`.gitignore`)
- [ ] Secrets rotated from any values used during development/testing
- [ ] CORS origins restricted to production domain(s)
- [ ] Docker containers running as non-root user

## Data

- [ ] All solar plants registered in plant registry
- [ ] Historical inverter data loaded and validated for each plant
- [ ] API adapters tested (eMIG, SolarGIS, NREL) with production keys
- [ ] Data quality backfill completed — no gaps in core metrics
- [ ] PVsyst monthly budgets imported for all active plants
- [ ] POA (Plane of Array) irradiance data imported where available
- [ ] Export limits configured per plant
- [ ] Tariff schedules entered for financial calculations
- [ ] Database integrity verified (`PRAGMA integrity_check` equivalent)
- [ ] Sample PDF report generated successfully for at least 2 plants

## Application

- [ ] Dashboard loads in < 2 seconds (first paint)
- [ ] All navigation pages load without errors
- [ ] PDF monthly reports generate correctly with charts and tables
- [ ] Alert rules configured and test alerts triggered
- [ ] Ticketing / Kanban board creates and moves tickets correctly
- [ ] Global search returns relevant results across all entities
- [ ] Data export (CSV/Excel) works for all exportable views
- [ ] Comparative analysis module produces correct cross-plant charts
- [ ] Portfolio map displays all plants at correct coordinates
- [ ] KPI cards show accurate, up-to-date values
- [ ] Anomaly detection produces reasonable flags on test data
- [ ] Degradation analysis runs without errors
- [ ] Loss waterfall chart renders with correct loss categories
- [ ] PR trending shows expected patterns against budget

## Infrastructure

- [ ] Docker containers start cleanly from `docker compose up -d`
- [ ] Health endpoint responds at `/_stcore/health`
- [ ] Daily database backup cron job scheduled (`scripts/backup_db.sh`)
- [ ] Application logs configured (stdout captured by Docker)
- [ ] Disk usage monitoring in place (alert at 85% usage)
- [ ] Container memory usage < 2 GB under normal operation
- [ ] Redis cache operational and connected
- [ ] Restart policy set to `unless-stopped`
- [ ] Backup restoration tested with `scripts/rollback.sh`
- [ ] `scripts/health_check.sh` runs successfully
- [ ] Cron job for health check configured (every 5 minutes)

## Documentation

- [ ] User Guide reviewed and up to date (`docs/USER_GUIDE.md`)
- [ ] Admin Guide reviewed and up to date (`docs/ADMIN_GUIDE.md`)
- [ ] API documentation available and accurate
- [ ] Runbook / operations guide prepared (deployment, rollback, backup)
- [ ] Architecture diagram current
- [ ] Known issues documented with workarounds

## Stakeholders

- [ ] Live demo completed with key stakeholders
- [ ] End-user training session(s) completed
- [ ] Primary support contact identified and communicated
- [ ] Feedback channel established (email, Slack, or issue tracker)
- [ ] Escalation path documented (P0–P3 severity levels)
- [ ] Go/No-Go decision recorded with stakeholder sign-off
- [ ] Post-launch review meeting scheduled (1 week after go-live)

---

## Sign-Off

| Role | Name | Date | Approval |
|------|------|------|----------|
| Project Lead | | | ☐ |
| Technical Lead | | | ☐ |
| Operations | | | ☐ |
| Business Owner | | | ☐ |

---

*All items must be checked before production deployment proceeds.*
