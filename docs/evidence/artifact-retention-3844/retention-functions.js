function getExpiration(retentionDays) {
    if (!retentionDays) {
        return undefined;
    }
    const maxRetentionDays = getRetentionDays();
    if (maxRetentionDays && maxRetentionDays < retentionDays) {
        warning(`Retention days cannot be greater than the maximum allowed retention set within the repository. Using ${maxRetentionDays} instead.`);
        retentionDays = maxRetentionDays;
    }
    const expirationDate = new Date();
    expirationDate.setDate(expirationDate.getDate() + retentionDays);
    return Timestamp.fromDate(expirationDate);
}
function getRetentionDays() {
    const retentionDays = process.env['GITHUB_RETENTION_DAYS'];
    if (!retentionDays) {
        return undefined;
    }
    const days = parseInt(retentionDays);
    if (isNaN(days)) {
        return undefined;
    }
    return days;
}