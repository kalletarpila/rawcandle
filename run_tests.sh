#!/bin/bash

# Testien ajamiskripti
# Käyttö: ./run_tests.sh [test-tyyppi]

set -e

echo "🧪 RawCandle Analysis Tests"
echo "=========================="

# Värit
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Funktiot
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Tarkista että pytest on asennettu
check_dependencies() {
    print_status "Tarkistetaan riippuvuudet..."
    
    # Virtuaaliympäristön Python
    VENV_PYTHON="./venv/bin/python"
    
    if ! [ -f "$VENV_PYTHON" ]; then
        print_error "Virtuaaliympäristö ei löydy: $VENV_PYTHON"
        exit 1
    fi
    
    if ! $VENV_PYTHON -c "import pytest" &> /dev/null; then
        print_warning "Pytest ei ole asennettu virtuaaliympäristössä. Asennetaan test-riippuvuudet..."
        $VENV_PYTHON -m pip install -r test-requirements.txt
    fi
    
    print_success "Riippuvuudet OK (virtuaaliympäristö)"
}

# Luo testiraporttikansio
setup_reports() {
    print_status "Luodaan raporttikansio..."
    mkdir -p reports
    print_success "Raporttikansio luotu"
}

# Suorita yksikkötestit
run_unit_tests() {
    print_status "Suoritetaan yksikkötestit..."
    
    $VENV_PYTHON -m pytest tests/test_database_manager.py tests/test_analyzer.py tests/test_analysis_view.py \
        -v \
        --cov=analysis \
        --cov-report=html:reports/coverage_unit \
        --cov-report=term \
        --html=reports/unit_tests.html \
        --self-contained-html \
        -m "not slow and not integration"
    
    if [ $? -eq 0 ]; then
        print_success "Yksikkötestit suoritettu onnistuneesti"
    else
        print_error "Yksikkötestit epäonnistuivat"
        return 1
    fi
}

# Suorita integraatiotestit
run_integration_tests() {
    print_status "Suoritetaan integraatiotestit..."
    
    python3 -m pytest tests/test_integration.py \
        -v \
        --cov=analysis \
        --cov-report=html:reports/coverage_integration \
        --cov-report=term \
        --html=reports/integration_tests.html \
        --self-contained-html \
        -m "integration"
    
    if [ $? -eq 0 ]; then
        print_success "Integraatiotestit suoritettu onnistuneesti"
    else
        print_error "Integraatiotestit epäonnistuivat"
        return 1
    fi
}

# Suorita suorituskykytestit
run_performance_tests() {
    print_status "Suoritetaan suorituskykytestit..."
    
    python3 -m pytest tests/test_performance.py \
        -v \
        --html=reports/performance_tests.html \
        --self-contained-html \
        -m "slow" \
        --benchmark-only \
        --benchmark-html=reports/benchmark.html
    
    if [ $? -eq 0 ]; then
        print_success "Suorituskykytestit suoritettu onnistuneesti"
    else
        print_error "Suorituskykytestit epäonnistuivat"
        return 1
    fi
}

# Suorita kaikki testit
run_all_tests() {
    print_status "Suoritetaan kaikki testit..."
    
    python3 -m pytest tests/ \
        -v \
        --cov=analysis \
        --cov=results \
        --cov-report=html:reports/coverage_all \
        --cov-report=term \
        --cov-report=xml:reports/coverage.xml \
        --html=reports/all_tests.html \
        --self-contained-html \
        --junitxml=reports/junit.xml
    
    if [ $? -eq 0 ]; then
        print_success "Kaikki testit suoritettu onnistuneesti"
    else
        print_error "Jotkut testit epäonnistuivat"
        return 1
    fi
}

# Suorita linting
run_linting() {
    print_status "Suoritetaan koodin laadun tarkistus..."
    
    # Flake8
    if command -v flake8 &> /dev/null; then
        print_status "Suoritetaan flake8..."
        flake8 analysis/ results/ tests/ --max-line-length=100 --exclude=venv,__pycache__ || true
    fi
    
    # Pylint
    if command -v pylint &> /dev/null; then
        print_status "Suoritetaan pylint..."
        pylint analysis/ results/ --exit-zero || true
    fi
    
    print_success "Linting suoritettu"
}

# Luo testiraportti
generate_report() {
    print_status "Luodaan yhteenveto..."
    
    cat > reports/test_summary.md << EOF
# Testiraportti

Generoitu: $(date)

## Testikattavuus
- Katso: reports/coverage_all/index.html

## Testiraportit
- Kaikki testit: reports/all_tests.html
- Yksikkötestit: reports/unit_tests.html
- Integraatiotestit: reports/integration_tests.html
- Suorituskykytestit: reports/performance_tests.html

## XML Raportit
- JUnit: reports/junit.xml
- Coverage: reports/coverage.xml

## Benchmark
- Suorituskyky: reports/benchmark.html
EOF
    
    print_success "Testiraportti luotu: reports/test_summary.md"
}

# Pääfunktio
main() {
    local test_type="${1:-all}"
    
    check_dependencies
    setup_reports
    
    case $test_type in
        "unit")
            run_unit_tests
            ;;
        "integration")
            run_integration_tests
            ;;
        "performance")
            run_performance_tests
            ;;
        "lint")
            run_linting
            ;;
        "all")
            run_linting
            run_unit_tests && run_integration_tests
            # Suorituskykytestit erikseen (voivat olla hitaita)
            print_status "Haluatko suorittaa suorituskykytestit? [y/N]"
            read -r response
            if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
                run_performance_tests
            fi
            ;;
        "quick")
            run_unit_tests
            ;;
        *)
            echo "Käyttö: $0 [unit|integration|performance|lint|all|quick]"
            echo ""
            echo "  unit         - Yksikkötestit"
            echo "  integration  - Integraatiotestit"
            echo "  performance  - Suorituskykytestit"
            echo "  lint         - Koodin laadun tarkistus"
            echo "  all          - Kaikki testit"
            echo "  quick        - Nopeat testit (vain yksikkötestit)"
            exit 1
            ;;
    esac
    
    generate_report
    
    print_success "Testit suoritettu! Katso raportit reports/ kansiosta."
    
    # Näytä kattavuusyhteenveto
    if [ -f "reports/coverage_all/index.html" ]; then
        print_status "Testikattavuus: file://$(pwd)/reports/coverage_all/index.html"
    fi
}

# Suorita pääfunktio
main "$@"