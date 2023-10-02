#!/usr/bin/env python3

import subprocess
import os
import sys
import json
import time

# Globals

oci_urlspace = "id8hewq9h9im" # Modify as needed, but this is the bucket used for the migration
bucket_name="azure-to-oci"
vm_name = str(sys.argv[1])
resource_group = str(sys.argv[2])
compartment_id = str(sys.argv[3])
subnet_id = str(sys.argv[4])

# check if the instance has more disks on Azure
def check_if_more_disks(vm_name):
    # Construct the Azure CLI command to get VM details
    cmd = f"az vm show -n {vm_name} -g {resource_group} --query \"[storageProfile.dataDisks]\""
    # Execute the command
    output = subprocess.check_output(cmd, shell=True)
    # Convert the output to a JSON object
    output = json.loads(output)
    # Check if the VM has more than one disk
    if len(output) > 0:
        return True
    else:
        return False
    
# Create a custom image from object stora
def oci_create_image(qcow2_file, vm_name):
    print("Creating OCI image...")
    cmd = f"oci compute image import from-object -bn {bucket_name} --display-name {vm_name} --compartment-id {compartment_id} --name {qcow2_file} --display-name {vm_name}"
    subprocess.run(cmd, shell=True, check=True)

def oci_create_block_volume(vm_name, oci_image_ocid):
    print("Creating OCI block volume...")
    cmd = f"oci bv volume create --availability-domain \"BvXz:US-ASHBURN-AD-1\" --compartment-id {compartment_id}"
    subprocess.run(cmd, shell=True, check=True)

# Function to get the OCI instance OCID
def get_oci_instance_ocid(vm_name):
    print("Getting OCI instance OCID...")
    cmd = f"oci compute instance list --compartment-id {compartment_id} --display-name {vm_name} --query \"data[0].id\""
    result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE)
    return result.stdout.decode('utf-8').strip().strip('"')

# Function to stop the instance in OCI
def oci_stop_instance(oci_instance_ocid):
    print("Stopping OCI instance...")
    cmd = f"oci compute instance action --action STOP --instance-id {oci_instance_ocid}"
    subprocess.run(cmd, shell=True, check=True)

# Function to start the instance in OCI
def oci_start_instance(oci_instance_ocid):
    print("Starting OCI instance...")
    cmd = f"oci compute instance action --action START --instance-id {oci_instance_ocid}"
    subprocess.run(cmd, shell=True, check=True)

# Function to attach the disk to the instance in OCI
def oci_attach_disk(oci_instance_ocid, oci_disk_ocid):
    print("Attaching OCI disk...")
    cmd = f"oci compute volume-attachment attach --instance-id {oci_instance_ocid} --type paravirtualized --volume-id {oci_disk_ocid}"
    subprocess.run(cmd, shell=True, check=True)

# Functio to get the custom image id in OCI
def get_oci_image_id(vm_name):
    print("Getting OCI image id...")
    cmd = f"oci compute image list --compartment-id {compartment_id} --display-name {vm_name} --query \"data[0].id\""
    result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE)
    return result.stdout.decode('utf-8').strip().strip('"')

# Function to export the VHD of the VM snapshot in Azure
def azure_export_vhd(snapshot_name):
    print("Exporting VHD from Azure...")
    cmd = "az snapshot grant-access --name " + snapshot_name + "-snapshot --resource-group " + resource_group + " --duration-in-seconds 3600 --query \"accessSas\""
    url = subprocess.run(cmd, shell=True, check=True, stdout=subprocess.PIPE)
    return url.stdout.decode('utf-8').strip("\"")

# Function to wget the VHD file from Azure
def get_vhd_azure_url(vm_name, snapshot_url):
    print("Downloading VHD from Azure...")
    cmd = f"wget --retry-connrefused --waitretry=1 --read-timeout=20 --timeout=15 -O {vhd_name} {snapshot_url}"
    #cmd = "wget --retry-connrefused --waitretry=1 --read-timeout=20 --timeout=15 -O " + vhd_name + " " +snapshot_url
    subprocess.run(cmd, shell=True, check=True)
    return vhd_name

# Function to convert VHD file to QCOW2 format
def convert_vhd_to_qcow2(vhd_name, qcow2_file):
    print("Converting VHD to QCOW2...")
    cmd = f"qemu-img convert -p -f vpc -O qcow2 {vhd_name} {qcow2_file}"
    subprocess.run(cmd, shell=True, check=True, stdout=subprocess.PIPE)
    return qcow2_file.stdout.decode('utf-8').strip("\"")

# Function to upload QCOW2 file to OCI object storage
def oci_upload_image(qcow2_file):
    print("Uploading QCOW2 to OCI object storage...")
    cmd = f"oci os object put -bn {bucket_name} --file {qcow2_file} -ns {oci_urlspace}"
    #cmd = "oci os object put -bn " + bucket_name + " --file " + qcow2_file + " -ns " + oci_urlspace
    subprocess.run(cmd, shell=True, check=True)
    return qcow2_file



if __name__ == "__main__":
    # if it has more disks, create a snashot of each disk
    if check_if_more_disks(vm_name):
        print("Creating snapshot of each disk...")
        cmd = f"az vm show --name {vm_name} --resource-group {resource_group} --query [\"storageProfile.dataDisks\"]"
        # Execute the command
        output = subprocess.check_output(cmd, shell=True)
        # Convert the output to a JSON object
        output = json.loads(output)
        # Stop the instance
        oci_instance_ocid = get_oci_instance_ocid(vm_name)
        #oci_stop_instance(oci_instance_ocid)
        # Iterate through each disk and create a snapshot
        for disk in output:
            disk_name = disk[0]['name']
            snapshot_name = f"{disk_name}-snapshot"
            cmd = f"az snapshot create --name {snapshot_name} --resource-group {resource_group} --source {disk_name}"
            subprocess.run(cmd, shell=True, check=True)
            # export the snapshot
            snapshot_url = azure_export_vhd(snapshot_name)
            # download the VHD file
            vhd_name = f"{disk_name}.vhd"
            get_vhd_azure_url(vm_name, snapshot_url)
            # convert the VHD file to QCOW2 format
            qcow2_file = {disk_name}.qcow2
            convert_vhd_to_qcow2(vhd_name, qcow2_file)
            # upload the QCOW2 file to OCI object storage
            oci_upload_image(qcow2_file)
            # import the QCOW2 file to custom images
            oci_create_image(qcow2_file, vm_name)
            # get the custom image id
            oci_image_ocid = get_oci_image_id(vm_name)
            # attach the disk to the instance in OCI
            oci_attach_disk(oci_instance_ocid, oci_image_ocid)
            # Attach the disk to the instance in OCI
            oci_attach_disk(oci_instance_ocid, qcow2_file)
        
        # Start the instance
        #oci_start_instance(oci_instance_ocid)
    else:
        print("No more disks to create snapshot")
        
