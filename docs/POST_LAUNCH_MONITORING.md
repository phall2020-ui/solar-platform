# Post-Launch Monitoring Guide

**Project:** Unified Solar Performance Platform  
**Effective From:** Go-Live Date

---

## Monitoring Metrics

| Metric | Target | Alert Threshold | Check Frequency |
|--------|--------|----------------|-----------------|
| App health endpoint | 200 OK | Any non-200 response | Every 5 min |
| Page load time (dashboard) | < 2s | > 5s | Every 15 min |
| Database file accessible | Readable | Inaccessible or corrupted | Every 5 min |
| Data freshness (latest inverter data) | < 24h old | > 48h stale | Every 30 min |
| Disk usage | < 70% | > 85% | Every 15 min |
| Container memory | < 1.5 GB | > 2 GB | Every 5 min |
| Docker container status | Running | Exited / Restarting | Every 5 min |
| Redis connectivity | Connected | Connection refused | Every 5 min |
| Log file size | < 200 MB | > 500 MB | Daily |
| Backup age | < 24h | > 48h (missed backup) | Daily |
| API adapter success rate | > 99% | < 95% | Hourly |
| PDF report generation | < 30s | > 60s or failure | On demand |

### Automated Monitoring

The `scripts/health_check.sh` script checks the core metrics above. Set up a cron job to run it every 5 minutes:

```bash
# Add to crontab (crontab -e)
*/5 * * * * /path/to/project/scripts/health_check.sh >> /var/log/solar_health.log 2>&1
```

For disk and log monitoring, the health check script will warn at configurable thresholds.

---

## Support Tiers

| Priority | Severity | Description | Response Time | Resolution Target | Examples |
|----------|----------|-------------|---------------|-------------------|----------|
| **P0** | Critical | System down, no workaround | 15 minutes | 1 hour | App unreachable, database corruption, data loss |
| **P1** | High | Major feature broken, workaround exists | 1 hour | 4 hours | Reports not generating, API adapter failing, dashboard blank |
| **P2** | Medium | Non-critical feature impacted | 4 hours | 1 business day | Single chart not rendering, export formatting issue, slow queries |
| **P3** | Low | Minor issue, cosmetic, or enhancement | 1 business day | 1 week | UI alignment, tooltip text, feature request |

### Escalation Path

1. **First responder:** On-call engineer — check health endpoint, review Docker logs
2. **Escalation 1 (15 min for P0):** Technical lead — database/infrastructure diagnosis
3. **Escalation 2 (1 hour for P0):** Project lead — stakeholder communication, rollback decision
4. **Escalation 3:** External support if infrastructure vendor involved

### On-Call Procedures

- Monitor the health check log: `tail -f /var/log/solar_health.log`
- Check Docker logs: `docker compose logs -f app --tail=100`
- Quick restart: `docker compose restart app`
- Full rollback: `./scripts/rollback.sh <backup_dir>`

---

## Week 1 Post-Launch Daily Actions

### Day 1 (Go-Live Day)
- [ ] Verify all services started successfully
- [ ] Confirm health check cron job is running
- [ ] Monitor application logs for errors continuously
- [ ] Verify data pull from API adapters completed
- [ ] Check dashboard loads with real production data
- [ ] Confirm backup ran successfully overnight

### Day 2
- [ ] Review overnight health check logs for any failures
- [ ] Check data freshness — latest data within expected window
- [ ] Monitor memory and disk usage trends
- [ ] Review any user-reported issues
- [ ] Verify PDF report generation with latest data
- [ ] Confirm daily backup completed and is restorable

### Day 3
- [ ] Analyze response time trends — any degradation?
- [ ] Check for any Docker container restarts
- [ ] Review Redis cache hit rates
- [ ] Gather initial user feedback
- [ ] Test alert rules fire correctly for configured thresholds

### Day 4
- [ ] Check disk space growth rate — project when 85% will be hit
- [ ] Review and rotate logs if needed
- [ ] Verify data quality scores across all plants
- [ ] Test rollback procedure in staging/dev if not already done
- [ ] Document any issues encountered and resolutions

### Day 5
- [ ] Full health review — compare all metrics against Day 1 baseline
- [ ] Prune old backups if not automated
- [ ] Summarize Week 1 issues and resolutions
- [ ] Prepare Week 1 post-launch report for stakeholders
- [ ] Schedule post-launch review meeting

### Day 6–7 (Weekend)
- [ ] Verify automated health checks continue running
- [ ] Spot-check data freshness
- [ ] Confirm no P0/P1 alerts triggered
- [ ] Review system resource usage over the week

---

## Monitoring Dashboard Recommendations

### Option 1: Simple — Log-Based Monitoring
Use `scripts/health_check.sh` output piped to a log file, monitored with `grep` or simple log-watching tools.
- **Pros:** Zero additional infrastructure, works immediately
- **Cons:** Manual review, no historical visualization

### Option 2: Intermediate — Uptime Kuma
[Uptime Kuma](https://github.com/louislam/uptime-kuma) is a self-hosted monitoring tool.
- Monitor the health endpoint with HTTP checks
- Set up notifications via email, Slack, or Discord
- Docker-based, easy to add to existing `docker-compose.yml`:

```yaml
uptime-kuma:
  image: louislam/uptime-kuma:1
  ports:
    - "3001:3001"
  volumes:
    - uptime-kuma-data:/app/data
  restart: unless-stopped
```

### Option 3: Intermediate — Grafana + Prometheus
For teams already using the Prometheus/Grafana stack:
- Export app metrics via a `/metrics` endpoint (add `prometheus_client` to the app)
- Scrape with Prometheus, visualize with Grafana
- Pre-built dashboards for Docker container metrics
- **Pros:** Rich visualization, alerting, historical trends
- **Cons:** Additional infrastructure to manage

### Option 4: Cloud — External Monitoring Service
Use a cloud monitoring service for zero-maintenance monitoring:
- **Better Uptime**, **Pingdom**, or **UptimeRobot** for HTTP health checks
- **Datadog** or **New Relic** for full observability (APM, logs, infrastructure)
- **Pros:** No infrastructure to manage, built-in alerting, mobile apps
- **Cons:** Monthly cost, data leaves your network

### Recommended Approach
Start with **Option 1** (log-based) on Day 1. If the deployment is business-critical, add **Option 2** (Uptime Kuma) within the first week for real-time alerts. Graduate to Option 3 or 4 as the team's monitoring needs grow.

---

## Key Commands Reference

```bash
# Health check (manual)
./scripts/health_check.sh

# View Docker container status
docker compose ps

# View application logs
docker compose logs -f app --tail=200

# View Redis logs
docker compose logs -f redis --tail=50

# Restart application
docker compose restart app

# Full deployment
./scripts/deploy.sh

# Backup database
./scripts/backup_db.sh

# Rollback to backup
./scripts/rollback.sh <backup_directory>

# Check disk usage
df -h .

# Check container resource usage
docker stats --no-stream
```
