#!/usr/bin/env python3
"""Build and verify a privately signed manager, using public kernel identity data."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import string
import struct
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent
HEADER = ROOT / "kernel/manager/manager_sign.h"
GKI_BASE = "d7260ca1e5c128061122924d0d48754e361e135c"
GKI_FILES = ["kernel/Kbuild", "kernel/Kconfig", "kernel/manager/apk_sign.c", "kernel/manager/manager_sign.h"]
SIGNING_PROPERTIES = ROOT / "manager/private-signing/signing.properties"
PACKAGE_PATTERN = re.compile(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+")


def select_package(requested=""):
    package = requested.strip()
    if not package:
        package = ".".join(
            "".join(secrets.choice(string.ascii_lowercase) for _ in range(8))
            for _ in range(3)
        )
    if len(package) > 255 or not PACKAGE_PATTERN.fullmatch(package):
        raise ValueError("Package must be a lowercase Android application ID, e.g. com.example.manager")
    return package


def expected_certificate():
    source = HEADER.read_text(encoding="utf-8")
    size = re.search(r"^#define EXPECTED_SIZE_BAKASU\s+(\S+)", source, re.M)
    digest = re.search(r'^#define EXPECTED_HASH_BAKASU\s+"([0-9a-f]{64})"', source, re.M)
    if not size or not digest:
        raise ValueError("Private certificate constants are missing from manager_sign.h")
    return int(size[1], 0), digest[1]


def check_certificate(certificate):
    size, digest = len(certificate), hashlib.sha256(certificate).hexdigest()
    if not 0 < size <= 1024:
        raise ValueError("Certificate exceeds the kernel's 1024-byte limit")
    if (size, digest) != expected_certificate():
        raise ValueError(f"Certificate does not match the kernel: size={size}, sha256={digest}")
    return {"certificate_size": size, "certificate_sha256": digest}


def length_prefixed(data, offset=0):
    if offset + 4 > len(data):
        raise ValueError("Truncated APK signing block")
    size = struct.unpack_from("<I", data, offset)[0]
    end = offset + 4 + size
    if end > len(data):
        raise ValueError("APK signing length exceeds its container")
    return data[offset + 4:end], end


def apk_certificate(apk):
    # Follow the same v2 -> signer -> signed data -> certificates path as apk_sign.c.
    with apk.open("rb") as stream:
        stream.seek(0, 2)
        file_size = stream.tell()
        stream.seek(max(0, file_size - 65557))
        tail = stream.read()
        eocd = next((
            index for index in range(len(tail) - 22, -1, -1)
            if tail[index:index + 4] == b"PK\x05\x06"
            and index + 22 + struct.unpack_from("<H", tail, index + 20)[0] == len(tail)
        ), None)
        if eocd is None:
            raise ValueError("APK ZIP footer is missing")
        central = struct.unpack_from("<I", tail, eocd + 16)[0]
        if central < 32 or central > file_size:
            raise ValueError("Invalid APK central directory")
        stream.seek(central - 24)
        footer = stream.read(24)
        size = struct.unpack_from("<Q", footer)[0]
        if footer[8:] != b"APK Sig Block 42" or not 24 <= size <= central - 8:
            raise ValueError("APK signing block is missing or malformed")
        stream.seek(central - size - 8)
        block = stream.read(size + 8)
    if struct.unpack_from("<Q", block)[0] != size:
        raise ValueError("APK signing block sizes disagree")
    offset, end, v2_blocks = 8, len(block) - 24, []
    while offset < end:
        if offset + 8 > end:
            raise ValueError("Truncated APK signing pair")
        length = struct.unpack_from("<Q", block, offset)[0]
        offset += 8
        if length < 4 or length > end - offset:
            raise ValueError("Invalid APK signing pair length")
        kind = struct.unpack_from("<I", block, offset)[0]
        if kind == 0x7109871A:
            v2_blocks.append(block[offset + 4:offset + length])
        elif kind != 0x42726577:
            raise ValueError(f"Kernel rejects signing block 0x{kind:08x}; use v2 only")
        offset += length
    if len(v2_blocks) != 1:
        raise ValueError("Kernel requires exactly one APK v2 block")
    signers, _ = length_prefixed(v2_blocks[0])
    signer, signer_end = length_prefixed(signers)
    if signer_end != len(signers):
        raise ValueError("Private manager must have one signer")
    signed_data, _ = length_prefixed(signer)
    _, digests_end = length_prefixed(signed_data)
    certificates, _ = length_prefixed(signed_data, digests_end)
    certificate, _ = length_prefixed(certificates)
    return certificate


def android_tool(name):
    sdk = os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME")
    if not sdk:
        raise ValueError("Set ANDROID_SDK_ROOT or ANDROID_HOME")
    directories = sorted((Path(sdk) / "build-tools").iterdir(), reverse=True)
    for directory in directories:
        if name == "apksigner":
            tool = directory / "lib/apksigner.jar"
        else:
            tool = directory / (name + (".exe" if os.name == "nt" else ""))
        if tool.is_file():
            return tool
    raise ValueError(f"Android SDK tool not found: {name}")


def verify_apk(apk, package="", require_ksud=False):
    info = check_certificate(apk_certificate(apk))
    with zipfile.ZipFile(apk) as archive:
        names = archive.namelist()
        if any(name.upper() == "META-INF/MANIFEST.MF" for name in names):
            raise ValueError("Kernel rejects APK v1 signatures")
        if require_ksud and not any(re.fullmatch(r"lib/[^/]+/libksud\.so", name) for name in names):
            raise ValueError("Final APK is missing its ksud binary")
    java_binary = "java.exe" if os.name == "nt" else "java"
    java = Path(os.environ["JAVA_HOME"]) / "bin" / java_binary if "JAVA_HOME" in os.environ else Path(java_binary)
    subprocess.run([str(java), "-jar", str(android_tool("apksigner")), "verify", str(apk)], check=True)
    badging = subprocess.check_output([str(android_tool("aapt2")), "dump", "badging", str(apk)], text=True)
    match = re.search(r"^package: name='([^']+)'", badging, re.M)
    if not match or (package and match[1] != package):
        raise ValueError("APK application ID does not match the selected manager package")
    if "application-label:'BakaSU Pro'" not in badging:
        raise ValueError("APK application label must be BakaSU Pro")
    with apk.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    info.update(apk=str(apk), package_name=match[1], apk_sha256=digest)
    return info


def read_signing_properties(properties):
    values = {}
    for line in properties.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            if "=" not in line:
                raise ValueError("Invalid signing properties entry")
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    required = ["KEYSTORE_FILE", "KEYSTORE_PASSWORD", "KEY_ALIAS", "KEY_PASSWORD"]
    if any(not values.get(key) for key in required):
        raise ValueError("Signing properties must define " + ", ".join(required))
    return {key: values[key] for key in required}


def configure_github_secrets(repository, properties):
    """Upload to an explicitly named repository, with every secret sent over stdin."""
    if not re.fullmatch(r"[a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+", repository):
        raise ValueError("Repository must be OWNER/REPO")
    gh = shutil.which("gh")
    if not gh:
        raise ValueError("Install GitHub CLI and run gh auth login first")
    values = read_signing_properties(properties)
    keystore = Path(values["KEYSTORE_FILE"])
    if not keystore.is_absolute():
        keystore = ROOT / "manager" / keystore
    java_home = os.environ.get("JAVA_HOME")
    keytool = str(Path(java_home) / "bin" / ("keytool.exe" if os.name == "nt" else "keytool")) if java_home else shutil.which("keytool")
    if not keytool:
        raise ValueError("Set JAVA_HOME to JDK 21, or add keytool to PATH")
    environment = os.environ.copy()
    environment["BAKASU_STORE_PASSWORD"] = values["KEYSTORE_PASSWORD"]
    certificate = subprocess.check_output([
        keytool, "-exportcert", "-keystore", str(keystore),
        "-alias", values["KEY_ALIAS"], "-storepass:env", "BAKASU_STORE_PASSWORD",
    ], env=environment)
    check_certificate(certificate)
    subprocess.run([gh, "auth", "status"], check=True, capture_output=True)
    secrets_to_set = {
        "KEYSTORE": base64.b64encode(keystore.read_bytes()).decode("ascii"),
        **{key: values[key] for key in ("KEYSTORE_PASSWORD", "KEY_ALIAS", "KEY_PASSWORD")},
    }
    for name, value in secrets_to_set.items():
        subprocess.run([gh, "secret", "set", name, "--repo", repository], input=value, text=True, check=True)
        print(f"Configured {name} for {repository}")


def export_gki_patch(output):
    patch = subprocess.check_output(["git", "diff", "--binary", GKI_BASE, "--", *GKI_FILES], cwd=ROOT)
    if not patch:
        raise ValueError("Private GKI changes are missing")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(patch)
    print(f"GKI patch written to {output}")


def build_manager(package, properties):
    environment = os.environ.copy()
    environment["KSU_PACKAGE_NAME"] = package
    for key, value in read_signing_properties(properties).items():
        environment[f"ORG_GRADLE_PROJECT_{key}"] = value
    executable = [str(ROOT / "manager/gradlew.bat")] if os.name == "nt" else ["bash", "./gradlew"]
    subprocess.run(executable + ["spotlessCheck", "assembleRelease", "lintRelease", "--no-configuration-cache"],
                   cwd=ROOT / "manager", env=environment, check=True)
    output = ROOT / "manager/app/build/outputs/apk/release"
    apks = sorted(output.glob("*.apk"))
    if not apks:
        raise ValueError("Gradle produced no release APK")
    result = [verify_apk(apk, package) for apk in apks]
    (output / "private-build.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


def prepare_signing():
    """Restore the user's CI key without printing it or putting passwords in argv."""
    required = ["KEYSTORE", "KEYSTORE_PASSWORD", "KEY_ALIAS", "KEY_PASSWORD"]
    if any(not os.environ.get(key) for key in required):
        raise ValueError("Configure KEYSTORE, KEYSTORE_PASSWORD, KEY_ALIAS and KEY_PASSWORD secrets")
    if any("\n" in os.environ[key] or "\r" in os.environ[key] for key in required[1:]):
        raise ValueError("Signing secrets cannot contain line breaks")
    directory = ROOT / "manager/private-signing"
    directory.mkdir(parents=True, exist_ok=True)
    keystore = directory / "bakasu-custom.jks"
    keystore.write_bytes(base64.b64decode(os.environ["KEYSTORE"], validate=True))
    java_home = Path(os.environ["JAVA_HOME"])
    certificate = directory / "manager-cert.der"
    subprocess.run([
        str(java_home / "bin" / ("keytool.exe" if os.name == "nt" else "keytool")),
        "-exportcert", "-keystore", str(keystore),
        "-alias", os.environ["KEY_ALIAS"], "-storepass:env", "KEYSTORE_PASSWORD",
        "-file", str(certificate),
    ], check=True)
    check_certificate(certificate.read_bytes())
    properties = {
        "KEYSTORE_FILE": keystore.as_posix(),
        "KEYSTORE_PASSWORD": os.environ["KEYSTORE_PASSWORD"],
        "KEY_ALIAS": os.environ["KEY_ALIAS"],
        "KEY_PASSWORD": os.environ["KEY_PASSWORD"],
    }
    (directory / "signing.properties").write_text(
        "".join(f"{key}={value}\n" for key, value in properties.items()), encoding="utf-8")
    config = {"signing": {
        "keystore_path": keystore.as_posix(),
        "key_alias": properties["KEY_ALIAS"],
        "keystore_pass": properties["KEYSTORE_PASSWORD"],
        "key_pass": properties["KEY_PASSWORD"],
    }}
    (directory / "repack-config.json").write_text(json.dumps(config), encoding="utf-8")
    print("Signing key matches the shared GKI/LKM certificate")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare-signing", help="Restore CI signing secrets and verify their public certificate")
    github = commands.add_parser("github-secrets", help="Configure the four signing secrets in your own GitHub repository")
    github.add_argument("--repo", required=True, help="Explicit destination in OWNER/REPO form")
    github.add_argument("--signing-properties", type=Path, default=SIGNING_PROPERTIES)
    patch = commands.add_parser("gki-patch", help="Export public GKI integration changes for upstream BakaSU 35229")
    patch.add_argument("--output", type=Path, default=ROOT / "dist/gki-manager-signature.patch")
    package = commands.add_parser("package", help="Print an explicit or newly randomized application ID")
    package.add_argument("--name", default="")
    certificate = commands.add_parser("check-cert", help="Verify public DER against the shared kernel header")
    certificate.add_argument("certificate", type=Path)
    apk = commands.add_parser("check-apk", help="Verify APK crypto, kernel signature compatibility and package")
    apk.add_argument("apk", type=Path)
    apk.add_argument("--name", default="")
    apk.add_argument("--require-ksud", action="store_true")
    build = commands.add_parser("build", help="Check and assemble the local Gradle manager (before ksud repacking)")
    build.add_argument("--name", default="")
    build.add_argument("--signing-properties", type=Path, default=SIGNING_PROPERTIES)
    args = parser.parse_args()
    if args.command == "prepare-signing":
        prepare_signing()
    elif args.command == "github-secrets":
        configure_github_secrets(args.repo, args.signing_properties)
    elif args.command == "gki-patch":
        export_gki_patch(args.output)
    elif args.command == "package":
        print(select_package(args.name))
    elif args.command == "check-cert":
        print(json.dumps(check_certificate(args.certificate.read_bytes()), indent=2))
    elif args.command == "check-apk":
        print(json.dumps(verify_apk(args.apk, args.name, args.require_ksud), indent=2))
    elif args.command == "build":
        selected = select_package(args.name)
        print(f"Manager package: {selected}", flush=True)
        build_manager(selected, args.signing_properties)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError, zipfile.BadZipFile) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
