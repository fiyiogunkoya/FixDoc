locals {
  tags = { Project = var.name_prefix, Owner = "fixdoc" }
}

module "app_a" {
  source      = "./modules/app"
  name_prefix = "${var.name_prefix}-a"
  # Intentionally omitting required vars: instance_type, subnet_cidr
}

module "app_b" {
  source      = "./modules/app"
  name_prefix = "${var.name_prefix}-b"
  # Intentionally omitting required vars: instance_type, subnet_cidr
}
