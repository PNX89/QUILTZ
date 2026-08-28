# The smallest configuration that can hold a state lock open long enough to look at it.
#
# A null_resource with a local-exec sleep, and a trigger so that changing one variable forces a
# replacement. The sleep is the whole point: an apply that finishes instantly gives nothing to
# sample pg_locks during, and an apply with NOTHING to do takes no lock at all, which is the
# trap src/quiltz/statelock.py is written around.
#
# This lives in the repository rather than in a scratch directory because the four transcripts
# that preceded it were produced by hand and could not be re-run by anybody, including their
# author. Evidence nothing regenerates is a claim about the past.

terraform {
  required_version = ">= 1.6"
  required_providers {
    null = { source = "hashicorp/null", version = "~> 3.2" }
  }
  backend "pg" {}
}

variable "tag" {
  description = "Change it to force a replacement, which is what gives the apply real work."
  type        = string
}

variable "seconds" {
  description = "How long the apply holds the lock. Long enough to sample pg_locks during it."
  type        = number
  default     = 20
}

resource "null_resource" "slow" {
  triggers = { tag = var.tag }

  provisioner "local-exec" {
    command = "sleep ${var.seconds}"
  }
}
