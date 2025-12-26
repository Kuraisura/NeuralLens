#!/bin/bash

echo "========================================"
echo "Neural Eye - Quick Setup"
echo "========================================"
echo ""

echo "Installing dependencies..."
python3 -m pip install -r requirements.txt

if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: Failed to install dependencies"
    echo "Please make sure Python 3 and pip are installed"
    exit 1
fi

echo ""
echo "========================================"
echo "Running automated setup..."
echo "========================================"
python3 setup.py

if [ $? -ne 0 ]; then
    echo ""
    echo "Setup encountered errors. Please check the output above."
    exit 1
fi

echo ""
echo "========================================"
echo "Setup Complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. Edit .env file (set your SECRET_KEY)"
echo "2. Run: python3 app.py"
echo ""
echo "For more info, read: IMPLEMENTATION_GUIDE.md"
echo ""
