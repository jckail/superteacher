output "cloud_sql_instance_connection_name" {
  description = "Use as Cloud Build substitution _CLOUD_SQL_INSTANCE after separate release approval."
  value       = google_sql_database_instance.app.connection_name
}

output "database_url_secret_name" {
  value = google_secret_manager_secret.database_url.secret_id
}

output "database_url_secret_version" {
  description = "Pin this version in a staged Cloud Run revision; latest changes during credential rotation."
  value       = google_secret_manager_secret_version.database_url.version
}
