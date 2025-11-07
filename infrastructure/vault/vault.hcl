# Vault configuration file
# This file is used for production-like Vault setup
# For dev mode, Vault uses command-line flags

storage "file" {
  path = "/vault/data"
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = 1
}

# Enable UI
ui = true

# Disable mlock for dev (not recommended for production)
disable_mlock = true

