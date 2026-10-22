#ifndef GAMES_MENU_H
#define GAMES_MENU_H

#include <Arduino.h>

// Existing API (do not break main.cpp)
void gamesLoop();
extern bool inGame;

// Optional new API for AppHost integration
void gamesEnter();
void gamesExit();

#endif