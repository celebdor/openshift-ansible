## OpenStack Kuryr

Install Kuryr components kuryr-cni on worker nodes.

## Requirements

* Ansible 2.2+
* Centos/ RHEL 7.3+

## Current Kuryr restrictions when used with Openshift

* OpenShift on OpenStack Newton or newer (only with Trunk ports)

## Key Ansible inventory configuration parameters

* ``kuryr_cni_link_interface=eth0``
