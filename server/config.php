<?php

function check_auth($config)
{
    $username = $_SERVER['PHP_AUTH_USER'] ?? '';
    $password = $_SERVER['PHP_AUTH_PW'] ?? '';

    if (
        $username !== ($config['username'] ?? '') ||
        $password !== ($config['password'] ?? '')
    ) {
        http_response_code(401);
        header('WWW-Authenticate: Basic realm="BayLang Server"');
        exit(json_encode(['error' => 'Unauthorized']));
    }
}

/**
 * Конфигурация сервера BayLang Task Server
 */
function config()
{
    return [
        // Пароль для basic auth
        'username' => 'admin',
        'password' => 'admin',

        // Путь к базе SQLite (создаётся автоматически)
        'db' => __DIR__ . '/data.sqlite',
    ];
}