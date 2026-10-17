@echo off
title EasyMind AI - Offline Programming Assistant Launcher
color 0B
echo ======================================================================
echo           EasyMind AI - Local Programming Learning Assistant          
echo ======================================================================
echo.
echo [1/3] Checking LM Studio connection (http://127.0.0.1:1234)...
echo       Please ensure LM Studio has a model loaded and Local Server started.
echo.
echo [2/3] Starting EasyMind AI Python Backend on port 5000...
cd /d "%~dp0"
start "EasyMind AI Backend" /min py app.py
timeout /t 2 /nobreak >nul
echo.
echo [3/3] Opening EasyMind AI in your default web browser...
start http://127.0.0.1:5000
echo.
echo ======================================================================
echo  EasyMind AI is now running at: http://127.0.0.1:5000
echo  Keep the backend console window open while using the application.
echo ======================================================================
timeout /t 5
