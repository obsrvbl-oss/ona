# Ubuntu Autoinstall

Link: https://canonical-subiquity.readthedocs-hosted.com/en/latest/intro-to-autoinstall.html

## DHCP/Static IP

* Automated DHCP: `nocloud-dhcp/user-data`
* Static IP: `nocloud-nodhcp/user-data` (there is
  *interactive-sections* which will invoke text UI to enter IP
  address manually or select the DHCP).


## Note

The `autoinstall.yaml` is expected to be present in the root of ISO
Image. Its format is missing main `autoinstall:` header in 22.04. In
later version (>= 24) it is expected to have different indentation:

```yaml
# Autoinstall configuration
autoinstall:
  version: 1

# Storage configuration with LVM
  storage:
    layout:
      name: lvm
...
```

