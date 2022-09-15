import os
import pytest

from lib import test_lib


@pytest.mark.order(1)
class TestsGeneric:
    @pytest.mark.run_on(['all'])
    def test_no_avc_denials(self, host):
        """
        Check there is no avc denials (selinux).
        """
        with host.sudo():
            assert 'no matches' in host.check_output('x=$(ausearch -m avc 2>&1 &); echo $x'), \
                'There should not be any avc denials (selinux)'

    @pytest.mark.run_on(['all'])
    def test_first_boot_time(self, host, instance_data):
        if instance_data['cloud'] == 'azure':
            max_boot_time_aws = 120
        elif host.system_info.arch == 'aarch64':
            max_boot_time_aws = 70
        else:
            max_boot_time_aws = 60

        boot_time = test_lib.get_host_last_boot_time(host)

        assert boot_time < max_boot_time_aws, f'First boot took more than {max_boot_time_aws} seconds'

    @pytest.mark.run_on(['all'])
    def test_bash_history_is_empty(self, host):
        users = [host.user().name, 'root']

        for u in users:
            file_path = f'/home/{u}/.bash_history'
            bash_history_file = host.file(file_path)
            if bash_history_file.exists:
                file_content_length = len(bash_history_file.content_string)
                assert file_content_length == 0, f'{file_path} must be empty or nonexistent'

    # TODO: Confirm if this test should be run in non-RHEL images
    @pytest.mark.run_on(['rhel'])
    def test_username(self, host, instance_data):
        for user in ['fedora', 'cloud-user']:
            with host.sudo():
                assert not host.user(user).exists, 'Unexpected username in instance'

            assert host.check_output('whoami') == instance_data['username']

    @pytest.mark.run_on(['all'])
    def test_console_is_redirected_to_ttys0(self, host):
        """
        Console output should be redirected to serial for HVM instances.
        """
        assert host.file('/proc/cmdline').contains('console=ttyS0'), \
            'Serial console should be redirected to ttyS0'

    # TODO: does this apply to fedora and centos
    @pytest.mark.run_on(['rhel'])
    def test_crashkernel_is_enabled_rhel(self, host):
        """
        Check that crashkernel is enabled in image.
        """
        product_release_version = float(host.system_info.release)

        if product_release_version < 9.0:
            expected_content = 'crashkernel=auto'
        else:
            with host.sudo():
                expected_content = host.check_output('kdumpctl showmem 2>&1 | sed -E "s/.*Reserved ([0-9]*).*/\1/"')

        with host.sudo():
            assert host.file('/proc/cmdline').contains(expected_content), \
                f'crashkernel must be enabled {expected_content}\n - {host.file("/proc/cmdline").content_string}\n - {host.check_output("kdumpctl showmem 2>&1")}'

    @pytest.mark.run_on(['all'])
    def test_cpu_flags_are_correct(self, host, instance_data):
        """
        Check various CPU flags for x86_64 instances.
        BugZilla 1061348
        """
        current_arch = host.system_info.arch

        if current_arch != 'x86_64':
            pytest.skip(f'Not applicable to {current_arch}')

        expected_flags = [
            'avx',
            'xsave',
        ]

        if instance_data['cloud'] == 'azure':
            expected_flags.append('pcid')

        with host.sudo():
            for flag in expected_flags:
                assert host.file('/proc/cpuinfo').contains(flag), \
                    f'Expected CPU flag "{flag}" not set'

    @pytest.mark.run_on(['all'])
    def test_rhgb_quiet_not_present_in_cmdline(self, host):
        """
        Check that there is no "rhgb" or "quiet" in /proc/cmdline.
        BugZilla 1122300
        """
        excluded_settings = [
            'rhgb',
            'quiet',
        ]

        with host.sudo():
            for setting in excluded_settings:
                assert not host.file('/proc/cmdline').contains(setting), \
                    f'{setting} must not be present in cmdline'

    @pytest.mark.run_on(['all'])
    def test_numa_settings(self, host):
        """
        Check if NUMA is enabled on supported image.
        """
        with host.sudo():
            assert host.run_test('dmesg | grep -i numa'), \
                'There is no NUMA information available'

            lscpu_numa_nodes = host.check_output("lscpu | grep -i 'NUMA node(s)' | awk -F' ' '{print $NF}'")
            dmesg_numa_nodes = host.check_output("dmesg | grep -i 'No NUMA'|wc -l")

            if int(lscpu_numa_nodes) > 1:
                assert dmesg_numa_nodes > 1, \
                    f'NUMA seems to be disabled, when it should be enabled (NUMA nodes: {lscpu_numa_nodes})'

    @pytest.mark.run_on(['rhel'])
    def test_cert_product_version_is_correct(self, host):
        """
        BugZilla 1938930
        Issue RHELPLAN-60817
        """
        product_version = float(host.system_info.release)

        if product_version < 8.0:
            rpm_to_check = 'redhat-release-server'
        else:
            rpm_to_check = 'redhat-release'

        with host.sudo():
            host.run_test(f'rpm -q {rpm_to_check}')

            cert_version = host.check_output('rct cat-cert /etc/pki/product-default/*.pem | grep Version')

            assert f'Version: {product_version}' in cert_version, \
                'Inconsistent version in pki certificate'

    @pytest.mark.run_on(['all'])
    def test_inittab_and_systemd(self, host):
        """
        Check default runlevel or systemd target.
        """
        kernel_release = host.check_output('uname -r')

        with host.sudo():
            if host.package('systemd').is_installed:
                assert '/lib/systemd/system/multi-user.target' in \
                       host.check_output('readlink -f /etc/systemd/system/default.target'), \
                    'Unexpected systemd default target'
            else:
                assert 'id:3:initdefault' in host.check_output("grep '^id:' /etc/inittab"), \
                    'Unexpected default inittab "id"'

                if 'el5' in kernel_release:
                    assert 'si::sysinit:/etc/rc.d/rc.sysinit' in host.check_output("grep '^si:' /etc/inittab"), \
                        'Unexpected default inittab "id"'

    # TODO: does this apply to centos
    # TODO: fix docstring
    @pytest.mark.run_on(['rhel', 'fedora'])
    def test_release_version(self, host):
        """
        Check if rhel provider matches /etc/redhat-release
        """
        if test_lib.is_rhel_atomic_host(host):
            pytest.skip('Not run in atomic images')

        product_version = float(host.system_info.release)

        release_file = 'redhat-release'
        if host.system_info.distribution == 'fedora':
            release_file = 'fedora-release'

        with host.sudo():
            command_to_run = "rpm -q --qf '%{VERSION}' --whatprovides " + release_file
            package_release_version = float(host.check_output(command_to_run))

        assert product_version == package_release_version, \
            f'product version ({product_version}) does not match package release version'

    @pytest.mark.run_on(['rhel'])
    def test_root_is_locked(self, host):
        """
        Check if root account is locked
        """
        with host.sudo():
            if test_lib.is_rhel_atomic_host(host):
                result = host.run('passwd -S root | grep -q Alternate').rc
            else:
                result = host.run('passwd -S root | grep -q LK').rc
        assert result == 0, 'Root account should be locked'

    @pytest.mark.run_on(['all'])
    def test_bash_in_shell_config(self, host):
        """
        Check for bash/nologin shells in /etc/shells
        """
        assert host.file('/etc/shells').contains('/bin/bash'), \
            '/bin/bash is not declared in /etc/shells'

    # TODO: create test case for aarch64 grub config file
    @pytest.mark.run_on(['rhel'])
    def test_grub_config(self, host):
        current_arch = host.system_info.arch
        if current_arch != 'x86_64':
            pytest.skip(f'Not applicable to {current_arch}')

        grub2_file = '/boot/grub2/grubenv'
        linked_to = grub2_file

        with host.sudo():
            if host.file('/sys/firmware/efi').exists:
                if float(host.system_info.release) < 8.0:
                    linked_to = '/boot/efi/EFI/redhat/grubenv'

            assert host.file(grub2_file).linked_to == linked_to

    @pytest.mark.run_on(['rhel'])
    def test_tty0_config(self, host):
        """
        BugZilla 1103344
        Check that "/etc/init/ttyS0.conf" and its backup file do not exist.
        """
        with host.sudo():
            assert not host.file('/etc/init/ttyS0.conf').exists, 'ttyS0.conf file should not exist'
            assert not host.file('/etc/init/ttyS0.bak').exists, 'ttyS0.conf backup file should not exist'

    @pytest.mark.run_on(['rhel'])
    def test_selinux_mode(self, host):
        """
        BugZilla 1960628
        SELinux should be in enforcing/targeted mode
        """
        if test_lib.is_rhel_sap(host):
            expected_mode = 'Permissive'
        else:
            expected_mode = 'Enforcing'

        expected_file_config = [
            f'SELINUX={expected_mode.lower()}',
            'SELINUXTYPE=targeted'
        ]

        selinux_config_file = '/etc/sysconfig/selinux'

        with host.sudo():
            assert host.check_output('getenforce') == expected_mode, \
                f'SELinux should be in {expected_mode} mode'

            for conf in expected_file_config:
                assert host.file(selinux_config_file).contains(conf), \
                    f'Expected "{conf}" to be in {selinux_config_file}'

    @pytest.mark.run_on(['all'])
    def test_rpm_v_unsatisfied_dependencies(self, host):
        """
        Check unsatisfied dependencies of pkgs.
        """

        with host.sudo():
            assert 'Unsatisfied' not in host.run('rpm -Va').stdout, \
                'There are unsatisfied dependencies'

    @pytest.mark.run_on(['all'])
    def test_no_sshkeys_knownhosts(self, host):
        """
        Verify no extra files under /root/.ssh/ except authorized_keys
        """
        with host.sudo():
            ssh_files = host.file('/root/.ssh/').listdir()
            assert 'authorized_keys' in ssh_files, 'authorized_keys is not in /root/.ssh/'
            assert len(ssh_files) == 1, 'there are extra files in /root/.ssh/'


@pytest.mark.order(1)
class TestsServices:
    @pytest.mark.run_on(['all'])
    def test_sshd(self, host):
        with host.sudo():
            sshd = host.service('sshd')
            assert sshd.is_running, 'ssh.service is not active'

            pass_auth_config_name = 'PasswordAuthentication'

            assert host.file('/etc/ssh/sshd_config').contains(f'^{pass_auth_config_name} no'), \
                f'{pass_auth_config_name} should be disabled (set to "no")'

    @pytest.mark.run_on(['rhel', 'centos'])
    def test_sysconfig_kernel(self, host):
        """
        UPDATEDEFAULT=yes and DEFAULTKERNEL=kernel should be set in /etc/sysconfig/kernel
        """
        if test_lib.is_rhel_atomic_host(host):
            pytest.skip('Not run in atomic images')

        kernel_config = '/etc/sysconfig/kernel'
        with host.sudo():
            assert host.file(kernel_config).contains('UPDATEDEFAULT=yes'), \
                f'UPDATEDEFAULT should be set to `yes` in {kernel_config}'
            assert host.file(kernel_config).contains('DEFAULTKERNEL=kernel'), \
                f'DEFAULTKERNEL should be set to `kernel` in {kernel_config}'


@pytest.mark.order(1)
class TestsCloudInit:
    @pytest.mark.run_on(['all'])
    def test_growpart_is_present_in_config(self, host, instance_data):
        """
        Make sure there is "growpart" in cloud_init_modules group in "/etc/cloud/cloud.cfg".
        For Azure instances, make sure there is also "mounts" in the config.
        BugZilla 966888
        """
        config_to_check = ['- growpart']
        if instance_data['cloud'] == 'azure':
            config_to_check.append('- mounts')

        for config in config_to_check:
            assert host.file('/etc/cloud/cloud.cfg').contains(config), \
                f'{config} must be present in cloud_init_modules'

    @pytest.mark.run_on(['rhel'])
    def test_wheel_group_not_set_to_default_user(self, host):
        """
        Make sure there is no wheel in default_user's group in "/etc/cloud/cloud.cfg".
        BugZilla 1549638
        Customer Case 01965459
        """
        assert not host.file('/etc/cloud/cloud.cfg').contains('wheel'), \
            'wheel should not be configured as default_user group'


@pytest.mark.pub
@pytest.mark.order(3)
class TestsYum:
    # TODO: confirm if this test needs to be deprecated
    @pytest.mark.run_on(['rhel', 'fedora'])
    def test_yum_repoinfo(self, host):
        if test_lib.is_rhel_atomic_host(host):
            pytest.skip('Not applicable to RHEL Atomic host')

        yum_command = 'yum repoinfo'

        with host.sudo():
            assert host.run_test(yum_command), 'Error while getting repo info'

            if host.system_info.distribution != 'fedora':
                assert 'Repo-pkgs          : 0' not in host.check_output(yum_command), \
                    'Unexpected number of repo pkgs (0)'

    @pytest.mark.run_on(['rhel'])
    def test_yum_package_install(self, host):
        with host.sudo():
            if 'rhui' not in host.check_output('rpm -qa'):
                pytest.skip('Not applicable to non-RHUI images')

            assert \
                host.run('yum clean all') and \
                host.run_test('yum repolist'), \
                'Could not get repo list correctly'

            return_code = host.run('yum check-update').rc
            assert return_code == 0 or return_code == 100, \
                'Could not check for yum updates'

            assert \
                host.run_test('yum search zsh') and \
                host.run_test('yum -y install zsh') and \
                host.run_test(r"rpm -q --queryformat '%{NAME}' zsh") and \
                host.run_test('rpm -e zsh'), \
                'yum packages installation failed'


@pytest.mark.order(1)
class TestsNetworking:
    # TODO: redo test with test infra module
    @pytest.mark.run_on(['all'])
    def test_dns_resolving_works(self, host):
        """
        Check if DNS resolving works.
        """
        assert host.run_test('ping -c 5 google-public-dns-a.google.com'), \
            'Public DNS resolution did not work'

    @pytest.mark.run_on(['all'])
    def test_ipv_localhost(self, host):
        """
        Check that localhost ipv6 and ipv4 are set in /etc/hosts.
        """
        expected_hosts = ['127.0.0.1   localhost localhost.localdomain localhost4 localhost4.localdomain4',
                          '::1         localhost localhost.localdomain localhost6 localhost6.localdomain6']
        with host.sudo():
            for expected_host in expected_hosts:
                assert host.file('/etc/hosts').contains(expected_host), \
                    '/etc/hosts does not contain ipv4 or ipv6 localhost'

    @pytest.mark.run_on(['rhel', 'fedora35', 'centos'])
    def test_eth0_network_adapter_setup(self, host):
        """
        Make sure that eht0 default adapter is correctly setup:
            1. NETWORKING=yes in /etc/sysconfig/network
            2. DEVICE=eth0 in /etc/sysconfig/network-scripts/ifcfg-eth0
        """
        device_name = 'eth0'

        with host.sudo():
            assert host.file('/etc/sysconfig/network').contains('^NETWORKING=yes'), \
                'Invalid networking setup'

            device_config_path = f'/etc/sysconfig/network-scripts/ifcfg-{device_name}'

            assert host.file(device_config_path).contains(f'^DEVICE=[{device_name}|\"{device_name}\"]'), \
                f'Unexpected device name. Expected: "{device_name}"'

    @pytest.mark.run_on(['rhel'])
    @pytest.mark.exclude_on(['rhel7.9', 'rhel8.4'])
    def test_network_manager_cloud_setup(self, host, instance_data):
        """
        BugZilla 1822853
        >=8.5: check NetworkManager-cloud-setup is installed and nm-cloud-setup.timer is setup for Azure and enabled
        """
        cloud_setup_base_path = '/usr/lib/systemd/system/nm-cloud-setup.service.d/'
        files_and_configs_by_cloud = {
            'aws': {
                'file_to_check': os.path.join(cloud_setup_base_path, '10-rh-enable-for-ec2.conf'),
                'expect_config': 'Environment=NM_CLOUD_SETUP_EC2=yes'
            },
            'azure': {  # COMPOSER-842
                'file_to_check': os.path.join(cloud_setup_base_path, '10-rh-enable-for-azure.conf'),
                'expect_config': 'Environment=NM_CLOUD_SETUP_AZURE=yes'
            }
        }

        # EXDSP-813
        if instance_data['cloud'] == 'azure' and float(host.system_info.release) == 8.5:
            pytest.skip("There is a known issue in RHEL 8.5 Azure images and won't be fixed.")

        with host.sudo():
            assert host.package('NetworkManager-cloud-setup').is_installed, \
                'NetworkManager-cloud-setup is expected to be installed in RHEL 8.5 and above'

            assert host.service('nm-cloud-setup').is_enabled, \
                'Expected cloud service is not enabled'

            file_to_check = files_and_configs_by_cloud[instance_data['cloud']]['file_to_check']
            expect_config = files_and_configs_by_cloud[instance_data['cloud']]['expect_config']

            assert host.file(file_to_check).contains(expect_config), \
                f'{expect_config} config is not set'

    @pytest.mark.run_on(['rhel'])
    def test_networkmanager_conf_plugins(self, host, instance_data):
        """
        Check /etc/NetworkManager/NetworkManager.conf
        """
        if instance_data['cloud'] == 'gcloud':
            pytest.skip('This test does not apply to GCP.')

        file_to_check = '/etc/NetworkManager/NetworkManager.conf'

        with host.sudo():
            assert host.file(file_to_check).contains('^plugins = ifcfg-rh,$'), \
                f'Unexpected or missing plugin(s) in {file_to_check}'


@pytest.mark.order(1)
class TestsSecurity:
    @pytest.mark.run_on(['rhel'])
    def test_firewalld_is_enabled(self, host, instance_data):
        """
        firewalld needs to be enabled in most clouds.
        """
        if instance_data['cloud'] == 'aws':
            pytest.skip('Test not applicable to AWS images')

        assert host.service('firewalld').is_enabled, \
            'firewalld should be enabled in most RHEL cloud images (except AWS AMIs)'


@pytest.mark.order(1)
@pytest.mark.run_on(['rhel'])
class TestsAuthConfig:
    @pytest.fixture(autouse=True)
    def skip_on_aws(self, host, instance_data):
        if instance_data['cloud'] == 'aws':
            pytest.skip("Auth test cases don't apply to AWS.")

    @pytest.mark.exclude_on(['rhel7.9'])
    def test_authselect_has_no_config(self, host):
        """
        Check authselect current
        """
        expected_output = 'No existing configuration detected.'
        assert expected_output in host.run('authselect current').stdout, \
            'authselect is expected to have no configuration'

    @pytest.mark.exclude_on(['rhel7.9'])
    def test_authselect_conf_files(self, host):
        authselect_dir = '/etc/authselect/'
        expected_config_files = ['custom', 'user-nsswitch.conf']
        current_files = host.file(authselect_dir).listdir()

        print(current_files)

        assert current_files == expected_config_files, \
            f'Unexpected result when listing files under {authselect_dir}'

        authselect_custom_dir = '/etc/authselect/custom/'
        assert len(host.file(authselect_custom_dir).listdir()) == 0, \
            f'Unexpected files found under {authselect_custom_dir}.' \
            f'This directory should be empty'

    def test_fingerprint_auth(self, host):
        """
        Check file /etc/pam.d/fingerprint-auth
        """
        self.__check_pam_d_file_content(host, 'fingerprint-auth')

    def test_password_auth(self, host):
        """
        Check file /etc/pam.d/password-auth
        """
        self.__check_pam_d_file_content(host, 'password-auth')

    def test_postlogin(self, host):
        """
        Check file /etc/pam.d/postlogin
        """
        self.__check_pam_d_file_content(host, 'postlogin')

    def test_smartcard_auth(self, host):
        """
        Check file /etc/pam.d/smartcard-auth
        """
        self.__check_pam_d_file_content(host, 'smartcard-auth')

    def test_system_auth(self, host):
        """
        Check file /etc/pam.d/system-auth
        """
        self.__check_pam_d_file_content(host, 'system-auth')

    def __check_pam_d_file_content(self, host, file_name):
        product_major_version = int(float(host.system_info.release))
        local_file = f'data/generic/{file_name}_rhel{product_major_version}'
        file_to_check = f'/etc/pam.d/{file_name}'

        assert test_lib.compare_local_and_remote_file(host, local_file, file_to_check), \
            f'{file_to_check} has unexpected content'


@pytest.mark.order(2)
class TestsKdump:
    @pytest.mark.pub
    @pytest.mark.run_on(['rhel'])
    def test_kdump_conf(self, host):
        """
        Check /etc/sysconfig/kdump and /etc/kdump.conf
        """
        sysconfig_kdump_conf = '/etc/sysconfig/kdump'
        kdump_conf = '/etc/kdump.conf'

        expected_kdump_config_data = self.__get_kdump_config_by_rhel_version(float(host.system_info.release))

        expected_sysconfig_kdump_content = expected_kdump_config_data['sysconfig_kdump']
        expected_kdump_content = expected_kdump_config_data['kdump_conf']

        with host.sudo():
            for item in expected_sysconfig_kdump_content:
                assert host.file(sysconfig_kdump_conf).contains(f'^{item}'), \
                    f'Unexpected kdump configuration in {sysconfig_kdump_conf}'

            for item in expected_kdump_content:
                assert host.file(kdump_conf).contains(f'^{item}'), \
                    f'Unexpected kdump configuration in {sysconfig_kdump_conf}'

    def __get_kdump_config_by_rhel_version(self, rhel_version):
        if rhel_version < 8.0:
            return {
                'sysconfig_kdump': [
                    'KDUMP_COMMANDLINE=""',
                    'KDUMP_COMMANDLINE_APPEND="irqpoll nr_cpus=1 reset_devices cgroup_disable=memory mce=off numa=off '
                    'udev.children-max=2 panic=10 acpi_no_memhotplug transparent_hugepage=never '
                    'nokaslr novmcoredd hest_disable"',
                    'KDUMP_COMMANDLINE_REMOVE="hugepages hugepagesz slub_debug kaslr"',
                    'KDUMP_IMG_EXT=""',
                    'KDUMP_IMG="vmlinuz"',
                    'KDUMP_KERNELVER=""',
                    'KEXEC_ARGS=""'
                ],
                'kdump_conf': [
                    'path /var/crash',
                    'core_collector makedumpfile -l --message-level 1 -d 31'
                ]
            }
        elif rhel_version < 9.0:
            conf = {
                'sysconfig_kdump': [
                    'KDUMP_KERNELVER=""',
                    'KDUMP_COMMANDLINE=""',
                    'KDUMP_COMMANDLINE_REMOVE="hugepages hugepagesz slub_debug quiet log_buf_len swiotlb"',
                    'KDUMP_COMMANDLINE_APPEND="irqpoll nr_cpus=1 reset_devices cgroup_disable=memory mce=off numa=off '
                    'udev.children-max=2 panic=10 rootflags=nofail acpi_no_memhotplug '
                    'transparent_hugepage=never nokaslr novmcoredd hest_disable"',
                    'KEXEC_ARGS="-s"',
                    'KDUMP_IMG="vmlinuz"',
                    'KDUMP_IMG_EXT=""'
                ],
                'kdump_conf': [
                    'path /var/crash',
                    'core_collector makedumpfile -l --message-level 7 -d 31'
                ]
            }
            if rhel_version >= 8.7:
                conf['sysconfig_kdump'][2] = 'KDUMP_COMMANDLINE_REMOVE="hugepages hugepagesz slub_debug quiet log_buf_len swiotlb ignition.firstboot"'
            return conf
        else:
            conf = {
                'sysconfig_kdump': [
                    'KDUMP_KERNELVER=""',
                    'KDUMP_COMMANDLINE=""',
                    'KDUMP_COMMANDLINE_REMOVE="hugepages hugepagesz slub_debug quiet log_buf_len swiotlb cma hugetlb_cma"',
                    'KDUMP_COMMANDLINE_APPEND="irqpoll nr_cpus=1 reset_devices cgroup_disable=memory mce=off '
                    'numa=off udev.children-max=2 panic=10 acpi_no_memhotplug transparent_hugepage=never '
                    'nokaslr hest_disable novmcoredd cma=0 hugetlb_cma=0"',
                    'KEXEC_ARGS="-s"',
                    'KDUMP_IMG="vmlinuz"',
                    'KDUMP_IMG_EXT=""'
                ],
                'kdump_conf': [
                    'path /var/crash',
                    'core_collector makedumpfile -l --message-level 7 -d 31'
                ]
            }
            if rhel_version >= 9.1:
                conf['sysconfig_kdump'][2] = 'KDUMP_COMMANDLINE_REMOVE="hugepages hugepagesz slub_debug quiet log_buf_len swiotlb cma hugetlb_cma ignition.firstboot"'
            return conf

    @pytest.mark.run_on(['rhel'])
    def test_kdump_status(self, host):
        """
        Verify that kdump is enabled
        """
        with host.sudo():
            assert 'Kdump is operational' in host.check_output('kdumpctl status 2>&1'), \
                'Kdump is not operational'


@pytest.mark.wait(120)
class TestsReboot:
    hostname_before_reboot_file = '/var/hostname_before_reboot'
    kmemleak_arg = 'kmemleak=on'

    def setup_before_reboot(self, host):
        with host.sudo():
            host.run(f'hostname > {self.hostname_before_reboot_file}')
            host.run_test(f'grubby --update-kernel=ALL --args="{self.kmemleak_arg}"')

    @pytest.mark.order(101)
    @pytest.mark.run_on(['all'])
    def test_launch_reboot(self, host, instance_data):
        self.setup_before_reboot(host)
        test_lib.reboot_host(host)

    @pytest.mark.order(102)
    @pytest.mark.run_on(['all'])
    def test_reboot_time(self, host, instance_data):
        """
        Check reboot time after 1st init.
        BugZilla 1776710, 1446698, 1446688
        """
        if instance_data['cloud'] == 'azure':
            max_boot_time_seconds = 60.0
        else:
            max_boot_time_seconds = 40.0

        boot_time = test_lib.get_host_last_boot_time(host)

        assert boot_time < max_boot_time_seconds, \
            f'Reboot took more than {max_boot_time_seconds} sec.'

    @pytest.mark.order(103)
    @pytest.mark.run_on(['all'])
    def test_reboot_keeps_current_hostname(self, host):
        """
        Check that reboot doesn't change the hostname
        """
        hostname_after_reboot = host.check_output('hostname')

        with host.sudo():
            assert host.file(self.hostname_before_reboot_file).contains(hostname_after_reboot), \
                'Instance hostname changed after reboot'

    # TODO: Review failure in RHEL 7.9, it may be related to a grubby bug
    @pytest.mark.order(104)
    @pytest.mark.run_on(['all'])
    def test_reboot_grubby(self, host):
        """
        Check that user can update boot parameter using grubby tool
        """
        file_to_check = '/proc/cmdline'

        with host.sudo():
            assert host.file(file_to_check).contains(self.kmemleak_arg), \
                f'Expected "{self.kmemleak_arg}" in "{file_to_check}"'

            host.run_test(f'grubby --update-kernel=ALL --remove-args="{self.kmemleak_arg}"')
