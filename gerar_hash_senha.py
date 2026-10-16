"""
Script utilitário: gera o hash bcrypt de uma senha para criar o super_admin
manualmente no banco de dados.

Uso:
    python gerar_hash_senha.py
"""

from werkzeug.security import generate_password_hash

senha = input("Digite a senha do super admin: ")
hash_gerado = generate_password_hash(senha)

print("\nHash gerado:")
print(hash_gerado)

print("\nUse este comando SQL para criar o super admin:\n")
print(
    "INSERT INTO users (nome, email, senha_hash, role) "
    f"VALUES ('Super Admin', 'admin@primefix.com', '{hash_gerado}', 'super_admin');"
)
