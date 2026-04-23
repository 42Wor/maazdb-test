dummy_data = "A" * 100
batch_size = 5
# Creates: "('A...A'), ('A...A'), ..."
values_clause = ", ".join([f"('{dummy_data}')"] * batch_size)
print(values_clause)
batch_query = f"INSERT INTO big_data (payload) VALUES {values_clause};"

print(len(batch_query))
