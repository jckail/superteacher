variable "project_id" {
  type        = string
  description = "Explicit target project; never inferred from gcloud configuration."
  default     = "portfolio-383615"
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "instance_name" {
  type    = string
  default = "superteacher-postgres"
}

variable "database_name" {
  type    = string
  default = "superteacher"
}

variable "database_user" {
  type    = string
  default = "superteacher_app"
}

variable "database_password" {
  type        = string
  description = "Supply securely at execution time; ephemeral and never stored in Terraform state or plans."
  sensitive   = true
  ephemeral   = true

  validation {
    condition     = length(var.database_password) >= 24
    error_message = "Use a unique password of at least 24 characters."
  }
}

variable "credential_version" {
  type        = number
  description = "Increment for every intentional password rotation; updates both SQL user and secret version."
  default     = 1

  validation {
    condition     = var.credential_version >= 1 && floor(var.credential_version) == var.credential_version
    error_message = "credential_version must be a positive integer."
  }
}

variable "cloud_run_service_account_email" {
  type        = string
  description = "Required existing runtime service account. This module does not create or select an account."

  validation {
    condition     = can(regex("^[a-zA-Z0-9._-]+@[a-zA-Z0-9.-]+\\.gserviceaccount\\.com$", var.cloud_run_service_account_email))
    error_message = "Supply the existing Cloud Run runtime service-account email."
  }
}

variable "availability_type" {
  type        = string
  description = "ZONAL is the lower-cost proposal; choose REGIONAL for high availability before applying."
  default     = "ZONAL"

  validation {
    condition     = contains(["ZONAL", "REGIONAL"], var.availability_type)
    error_message = "Choose ZONAL or REGIONAL."
  }
}

variable "tier" {
  type        = string
  description = "Dedicated-core Enterprise tier; resize after measuring workload."
  default     = "db-custom-1-3840"
}

variable "disk_autoresize_limit_gb" {
  type        = number
  description = "Storage growth ceiling; alert and raise before reaching this limit."
  default     = 100

  validation {
    condition     = var.disk_autoresize_limit_gb >= 20
    error_message = "Storage ceiling must be at least the initial 20 GB."
  }
}
