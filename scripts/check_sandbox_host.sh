#!/usr/bin/env bash
# ==============================================================================
# MediCode Sandbox Host Compatibility Checker
# Validates host kernel, cgroups v1 hierarchy, and Docker privileged isolate readiness
# ==============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}======================================================${NC}"
echo -e "${BLUE}    MediCode & Judge0 CE Host Compatibility Check    ${NC}"
echo -e "${BLUE}======================================================${NC}"

FAILURES=0
WARNINGS=0

# 1. Check Operating System
OS="$(uname -s)"
echo -n "[1/5] Checking OS: $OS ... "
if [ "$OS" != "Linux" ]; then
    echo -e "${YELLOW}WARNING${NC}"
    echo -e "       Host OS is $OS. Judge0 CE requires a Linux host for isolate sandboxing."
    echo -e "       If developing locally on macOS/Windows, ensure Docker Desktop uses WSL2/Linux VM."
    WARNINGS=$((WARNINGS + 1))
else
    echo -e "${GREEN}OK${NC}"
fi

# 2. Check cgroup hierarchy (Judge0 isolate requires cgroups v1)
echo -n "[2/5] Checking cgroup v1 controllers ... "
if [ -d "/sys/fs/cgroup/memory" ] && [ -d "/sys/fs/cgroup/cpu" ]; then
    echo -e "${GREEN}OK (cgroup v1 active)${NC}"
else
    echo -e "${RED}FAILED${NC}"
    echo -e "       ${RED}cgroup v1 controllers for memory/cpu were NOT detected.${NC}"
    echo -e "       Judge0 CE relies on 'isolate', which in standard releases requires cgroup v1."
    echo -e "       On Ubuntu 22.04 / Debian 11+, enable cgroup v1 by adding:"
    echo -e "         ${YELLOW}GRUB_CMDLINE_LINUX=\"systemd.unified_cgroup_hierarchy=0\"${NC}"
    echo -e "       to ${YELLOW}/etc/default/grub${NC}, then run ${YELLOW}sudo update-grub${NC} and reboot."
    FAILURES=$((FAILURES + 1))
fi

# 3. Check memory swap accounting
echo -n "[3/5] Checking memory swap accounting ... "
if [ -f "/sys/fs/cgroup/memory/memory.memsw.limit_in_bytes" ]; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${YELLOW}WARNING${NC}"
    echo -e "       Swap accounting not enabled. If sandbox memory limits misbehave, add:"
    echo -e "         ${YELLOW}cgroup_enable=memory swapaccount=1${NC}"
    echo -e "       to GRUB kernel parameters."
    WARNINGS=$((WARNINGS + 1))
fi

# 4. Check Docker daemon availability
echo -n "[4/5] Checking Docker installation ... "
if command -v docker &> /dev/null; then
    DOCKER_VERSION=$(docker --version)
    echo -e "${GREEN}OK ($DOCKER_VERSION)${NC}"
else
    echo -e "${RED}FAILED${NC}"
    echo -e "       Docker is not installed or not in PATH."
    FAILURES=$((FAILURES + 1))
fi

# 5. Check Docker compose availability
echo -n "[5/5] Checking Docker Compose ... "
if docker compose version &> /dev/null; then
    COMPOSE_VERSION=$(docker compose version)
    echo -e "${GREEN}OK ($COMPOSE_VERSION)${NC}"
elif command -v docker-compose &> /dev/null; then
    COMPOSE_VERSION=$(docker-compose --version)
    echo -e "${GREEN}OK ($COMPOSE_VERSION)${NC}"
else
    echo -e "${RED}FAILED${NC}"
    echo -e "       Docker compose plugin or docker-compose binary not found."
    FAILURES=$((FAILURES + 1))
fi

echo -e "${BLUE}------------------------------------------------------${NC}"
if [ $FAILURES -eq 0 ]; then
    echo -e "${GREEN}Host check PASSED with $WARNINGS warning(s). Environment is ready for Judge0 CE.${NC}"
    exit 0
else
    echo -e "${RED}Host check FAILED with $FAILURES error(s) and $WARNINGS warning(s).${NC}"
    echo -e "Please address the cgroup/Docker requirements above before starting the sandbox."
    exit 1
fi
