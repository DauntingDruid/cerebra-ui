#!/bin/bash

# Script to run accessibility tests against Docker services
# Usage: ./frontend_test/run-accessibility-tests.sh

echo "Checking Docker services..."

# Check if Docker services are running
if ! docker compose ps | grep -q "open-webui.*Up"; then
    echo "ERROR: Docker services are not running!"
    echo "Please start them first with: docker compose up -d"
    exit 1
fi

echo "Docker services are running"

# Check if service is accessible
if ! curl -s http://localhost:3000/health > /dev/null 2>&1; then
    echo "WARNING: Service at http://localhost:3000 may not be ready"
    echo "Waiting 5 seconds for service to be ready..."
    sleep 5
fi

echo "Running accessibility tests..."
echo ""

# Run Cypress tests
npx cypress run --spec "cypress/e2e/accessibility.cy.ts" "${@}"

exit_code=$?

if [ $exit_code -eq 0 ]; then
    echo ""
    echo "All accessibility tests passed!"
else
    echo ""
    echo "Some tests failed. Check the output above for details."
fi

exit $exit_code

