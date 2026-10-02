locals {
  labels = { application = "superteacher", managed_by = "terraform" }
  # urlencode also handles passwords with @, :, /, ?, #, % and other URI delimiters.
  database_url = "postgresql+psycopg://${urlencode(var.database_user)}:${urlencode(var.database_password)}@/${urlencode(var.database_name)}?host=${urlencode("/cloudsql/${google_sql_database_instance.app.connection_name}")}"
}

resource "google_project_service" "required" {
  for_each = toset(["sqladmin.googleapis.com", "secretmanager.googleapis.com"])
  project  = var.project_id
  service  = each.value
  # These APIs may be shared by unrelated services in this project.
  disable_on_destroy = false
}

resource "google_sql_database_instance" "app" {
  project             = var.project_id
  name                = var.instance_name
  region              = var.region
  database_version    = "POSTGRES_17"
  deletion_protection = true

  settings {
    edition                     = "ENTERPRISE"
    tier                        = var.tier
    availability_type           = var.availability_type
    deletion_protection_enabled = true
    connector_enforcement       = "REQUIRED"
    disk_type                   = "PD_SSD"
    disk_size                   = 20
    disk_autoresize             = true
    disk_autoresize_limit       = var.disk_autoresize_limit_gb
    user_labels                 = local.labels

    ip_configuration {
      ipv4_enabled   = true
      ssl_mode       = "ENCRYPTED_ONLY"
      server_ca_mode = "GOOGLE_MANAGED_INTERNAL_CA"
      # No authorized_networks: only IAM-authorized Cloud SQL connectors/proxy.
    }

    backup_configuration {
      enabled                        = true
      start_time                     = "10:00"
      location                       = var.region
      point_in_time_recovery_enabled = true
      transaction_log_retention_days = 7
      backup_retention_settings {
        retained_backups = 14
        retention_unit   = "COUNT"
      }
    }

    maintenance_window {
      day          = 7
      hour         = 11
      update_track = "stable"
    }
  }

  lifecycle {
    prevent_destroy = true
    # Cloud SQL cannot shrink a disk. Retain actual size after automatic growth.
    ignore_changes = [settings[0].disk_size]
  }

  depends_on = [google_project_service.required]
}

resource "google_sql_database" "app" {
  project  = var.project_id
  instance = google_sql_database_instance.app.name
  name     = var.database_name

  lifecycle {
    prevent_destroy = true
  }
}

# See the mandatory SQL privilege hardening step in docs/CLOUD_SQL_PLAN.md.
# The Cloud SQL Admin API initially gives built-in users cloudsqlsuperuser.
resource "google_sql_user" "app" {
  project             = var.project_id
  instance            = google_sql_database_instance.app.name
  name                = var.database_user
  type                = "BUILT_IN"
  password_wo         = var.database_password
  password_wo_version = var.credential_version
  deletion_policy     = "ABANDON"

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_secret_manager_secret" "database_url" {
  project   = var.project_id
  secret_id = "superteacher-database-url"
  labels    = local.labels

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_version" "database_url" {
  secret                 = google_secret_manager_secret.database_url.id
  secret_data_wo         = local.database_url
  secret_data_wo_version = var.credential_version
  deletion_policy        = "ABANDON"

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [google_sql_user.app, google_sql_database.app]
}

# Additive IAM members preserve other grants; never authoritative bindings.
resource "google_project_iam_member" "cloud_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${var.cloud_run_service_account_email}"
}

resource "google_secret_manager_secret_iam_member" "database_url_reader" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.database_url.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.cloud_run_service_account_email}"
}
