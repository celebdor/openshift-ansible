#!/usr/bin/env python
"""
This is an Ansible dynamic inventory for OpenStack.

It requires your OpenStack credentials to be set in clouds.yaml or your shell
environment.

"""

from __future__ import print_function

import json

import shade


def build_inventory():
    '''Build the dynamic inventory.'''
    cloud = shade.openstack_cloud()

    inventory = {}

    # TODO(shadower): filter the servers based on the `OPENSHIFT_CLUSTER`
    # environment variable.
    cluster_hosts = [
        server for server in cloud.list_servers()
        if 'metadata' in server and 'clusterid' in server.metadata]

    masters = [server.name for server in cluster_hosts
               if server.metadata['host-type'] == 'master']

    etcd = [server.name for server in cluster_hosts
            if server.metadata['host-type'] == 'etcd']
    if not etcd:
        etcd = masters

    infra_hosts = [server.name for server in cluster_hosts
                   if server.metadata['host-type'] == 'node' and
                   server.metadata['sub-host-type'] == 'infra']

    app = [server.name for server in cluster_hosts
           if server.metadata['host-type'] == 'node' and
           server.metadata['sub-host-type'] == 'app']

    nodes = list(set(masters + infra_hosts + app))

    dns = [server.name for server in cluster_hosts
           if server.metadata['host-type'] == 'dns']

    load_balancers = [server.name for server in cluster_hosts
                      if server.metadata['host-type'] == 'lb']

    osev3 = list(set(nodes + etcd + load_balancers))

    inventory['cluster_hosts'] = {'hosts': [s.name for s in cluster_hosts]}
    inventory['OSEv3'] = {'hosts': osev3}
    inventory['masters'] = {'hosts': masters}
    inventory['etcd'] = {'hosts': etcd}
    inventory['nodes'] = {'hosts': nodes}
    inventory['infra_hosts'] = {'hosts': infra_hosts}
    inventory['app'] = {'hosts': app}
    inventory['dns'] = {'hosts': dns}
    inventory['lb'] = {'hosts': load_balancers}

    for server in cluster_hosts:
        if 'group' in server.metadata:
            group = server.metadata.group
            if group not in inventory:
                inventory[group] = {'hosts': []}
            inventory[group]['hosts'].append(server.name)

    inventory['_meta'] = {'hostvars': {}}

    for server in cluster_hosts:
        ssh_ip_address = server.public_v4 or server.private_v4
        hostvars = {
            'ansible_host': ssh_ip_address
        }

        public_v4 = server.public_v4 or server.private_v4
        if public_v4:
            hostvars['public_v4'] = public_v4
        # TODO(shadower): what about multiple networks?
        if server.private_v4:
            hostvars['private_v4'] = server.private_v4

        node_labels = server.metadata.get('node_labels')
        if node_labels:
            hostvars['openshift_node_labels'] = node_labels

        inventory['_meta']['hostvars'][server.name] = hostvars

    kuryr_vars = _get_kuryr_vars(cloud)
    if kuryr_vars:
        inventory['OSEv3']['vars'] = kuryr_vars

    return inventory


def _get_kuryr_vars(cloud_client):
    """Returns a dictionary of Kuryr variables resulting of heat stacking"""
    # TODO: Filter the cluster stack with tags once it is supported in shade
    hardcoded_cluster_name = 'openshift.example.com'
    stack = cloud_client.user_cloud.get_stack(hardcoded_cluster_name)
    if stack['stack_status'] != 'CREATE_COMPLETE':
        return None

    settings = {}
    # TODO: verify this shade block and complete missing vars
    settings['kuryr_openstack_pod_subnet_id'] = (
        stack['outputs']['pod_subnet']['output_value'])
    settings['kuryr_openstack_worker_nodes_subnet_id'] = (
        stack['outputs']['vm_subnet']['output_value'])
    settings['kuryr_openstack_service_subnet_id'] = (
        stack['outputs']['service_subnet']['output_value'])
    settings['kuryr_openstack_pod_sg_id'] = (
        stack['outputs']['pod_sg_id']['output_value'])
    settings['kuryr_openstack_pod_project_id'] = (
        cloud_client.current_project_id)

    settings['kuryr_openstack_auth_url'] = cloud_client.auth['auth_url']
    settings['kuryr_openstack_username'] = cloud_client.auth['username']
    settings['kuryr_openstack_password'] = cloud_client.auth['password']
    settings['kuryr_openstack_user_domain_name'] = (
        cloud_client.auth['user_domain_id'])
    settings['kuryr_openstack_project_id'] = cloud_client.current_project_id
    settings['kuryr_openstack_project_domain_name'] = (
        cloud_client.auth['project_domain_id'])


if __name__ == '__main__':
    print(json.dumps(build_inventory(), indent=4, sort_keys=True))
