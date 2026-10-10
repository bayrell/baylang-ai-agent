<?php

/**
 * Конфигурация сервера BayLang Task Server
 */
return [
    // Пароль для basic auth (пользователь игнорируется, важен только пароль)
    'password' => 'admin',

    // Путь к базе SQLite (создаётся автоматически)
    'db' => __DIR__ . '/data.sqlite',
];
