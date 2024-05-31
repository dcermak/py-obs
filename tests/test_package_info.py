import pytest

from py_obs.project import PackageSourceInfo, fetch_package_info
from tests.conftest import OSC_FROM_ENV_T


@pytest.mark.vcr(filter_headers=["authorization", "openSUSE_session"])
@pytest.mark.asyncio
async def test_nginx_from_factory(osc_from_env: OSC_FROM_ENV_T) -> None:
    async for osc in osc_from_env:
        assert await fetch_package_info(
            osc, "openSUSE:Factory", "nginx"
        ) == PackageSourceInfo(
            package="nginx",
            rev="89",
            vrev="2",
            srcmd5="6c3e9cd13302b4b3431557c2b8851ceb",
            originproject=None,
            filename="nginx.spec",
            name="nginx",
            version="1.25.5",
            release="0",
            subpacks=["nginx", "nginx-source"],
            deps=[
                "nginx-macros",
                "gcc-c++",
                "libatomic-ops-devel",
                "pkgconfig",
                "sysuser-shadow",
                "sysuser-tools",
                "vim",
                "pkgconfig(gdlib)",
                "pkgconfig(libpcre2-8)",
                "pkgconfig(libxslt)",
                "pkgconfig(openssl)",
                "pkgconfig(systemd)",
                "pkgconfig(zlib)",
            ],
        )


@pytest.mark.vcr(filter_headers=["authorization", "openSUSE_session"])
@pytest.mark.asyncio
async def test_mariadb_from_SLES(osc_from_env: OSC_FROM_ENV_T) -> None:
    async for osc in osc_from_env:
        assert (
            await fetch_package_info(osc, "SUSE:SLE-15-SP5:Update", "mariadb")
        ) == PackageSourceInfo(
            package="mariadb",
            rev="8",
            vrev="3.30",
            srcmd5="7aa79a6c980be4ec33c71f066b181ab6",
            filename="mariadb.spec",
            originproject="SUSE:SLE-15-SP4:Update",
            # linked project="SUSE:SLE-15-SP5:GA" package="mariadb"/="
            # linked project="SUSE:SLE-15-SP4:Update" package="mariadb"/="
            # linked project="SUSE:SLE-15-SP5:Update" package="mariadb.30339"/="
            # linked project="SUSE:SLE-15-SP5:GA" package="mariadb.30339"/="
            # linked project="SUSE:SLE-15-SP4:Update" package="mariadb.30339"/="
            name="mariadb",
            version="10.6.15",
            release="0",
            subpacks=[
                "mariadb",
                "libmariadbd19",
                "libmariadbd-devel",
                "mariadb-rpm-macros",
                "mariadb-client",
                "mariadb-errormessages",
                "mariadb-bench",
                "mariadb-test",
                "mariadb-tools",
            ],
            deps=[
                "bison",
                "cmake",
                "dos2unix",
                "fdupes",
                "gcc-c++",
                "krb5-devel",
                "libaio-devel",
                "libarchive-devel",
                "libbz2-devel",
                "libedit-devel",
                "libevent-devel",
                "liblz4-devel",
                "libtool",
                "libxml2-devel",
                "ncurses-devel",
                "openssl-devel",
                "pam-devel",
                "pcre2-devel",
                "pkgconfig",
                "procps",
                "python3",
                "sqlite",
                "sysuser-tools",
                "tcpd-devel",
                "time",
                "unixODBC-devel",
                "zlib-devel",
                "perl(Data::Dumper)",
                "perl(Env)",
                "perl(Exporter)",
                "perl(Fcntl)",
                "perl(File::Temp)",
                "perl(Getopt::Long)",
                "perl(IPC::Open3)",
                "perl(Memoize)",
                "perl(Socket)",
                "perl(Symbol)",
                "perl(Sys::Hostname)",
                "perl(Test::More)",
                "perl(Time::HiRes)",
                "pkgconfig(libsystemd)",
                "-user(mysql)",
                "lzo-devel",
                "judy-devel",
                "boost-devel",
            ],
            prereqs=["permissions", "user(mysql)"],
        )


@pytest.mark.vcr(filter_headers=["authorization", "openSUSE_session"])
@pytest.mark.asyncio
async def test_errors_out_on_non_spec_packages(osc_from_env: OSC_FROM_ENV_T) -> None:
    prj, pkg = "openSUSE:Factory", "spack-image"
    async for osc in osc_from_env:
        with pytest.raises(ValueError) as val_err_ctx:
            await fetch_package_info(osc, prj, pkg)

        assert (
            f"OBS could not parse the package {prj}/{pkg}: no file found for build type 'spec'"
            in str(val_err_ctx.value)
        )
