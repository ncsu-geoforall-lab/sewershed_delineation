"""Helper functions for the notebooks"""

import json

import grass.script as gs


def quote_from_type(column_type):
    """Returns quote if column values need to be quoted based on their type

    Defaults to quoting for unknown types and no quoting for falsely values,
    i.e., unknown types are assumed to be in need of quoting while missing type
    information is assumed to be associated with numbers which don't need quoting.
    """
    if not column_type or column_type.upper() in [
        "INT",
        "INTEGER",
        "SMALLINT",
        "REAL",
        "DOUBLE",
        "DOUBLE PRECISION",
    ]:
        return ""
    return "'"


def updates_to_sql(table, updates):
    """Create SQL from a list of dicts with column, value, where"""
    sql = ["BEGIN TRANSACTION"]
    for update in updates:
        quote = quote_from_type(update.get("type", None))
        sql.append(
            f"UPDATE {table} SET {update['column']} = {quote}{update['value']}{quote} "
            f"WHERE {update['where']};"
        )
    sql.append("END TRANSACTION")
    return "\n".join(sql)


def column_value_to_where(column, value, *, quote):
    """Create SQL where clause without the where keyword for column and its value"""
    if value is None:
        return f"{column} IS NULL"
    if quote:
        return f"{column}='{value}'"
    return f"{column}={value}"


def aggregate_attributes_sql(
    input_name,
    input_layer,
    column,
    quote_column,
    columns_to_aggregate,
    methods,
    result_columns,
):
    """Aggregate values in selected columns grouped by column using SQL backend"""
    if len(columns_to_aggregate) != len(result_columns):
        raise ValueError(
            "Number of columns_to_aggregate and result_columns must be the same"
        )
    if methods and len(columns_to_aggregate) != len(methods):
        raise ValueError("Number of columns_to_aggregate and methods must be the same")
    if not methods:
        for result_column in result_columns:
            if " " not in result_column:
                raise ValueError(
                    f"Column {result_column} from result_columns without type"
                )
    if methods:
        select_columns = [
            f"{method}({agg_column})"
            for method, agg_column in zip(methods, columns_to_aggregate)
        ]
        column_types = [
            "INTEGER" if method == "count" else "DOUBLE" for method in methods
        ] * len(columns_to_aggregate)
    else:
        select_columns = columns_to_aggregate
        column_types = None

    records = json.loads(
        gs.read_command(
            "v.db.select",
            map=input_name,
            layer=input_layer,
            columns=",".join([column] + select_columns),
            group=column,
            format="json",
        )
    )["records"]
    updates = []
    add_columns = []
    if column_types:
        for result_column, column_type in zip(result_columns, column_types):
            add_columns.append(f"{result_column} {column_type}")
    else:
        # Column types are part of the result column name list.
        add_columns = result_columns.copy()  # Ensure we have our own copy.
        # Split column definitions into two lists.
        result_columns = []
        column_types = []
        for definition in add_columns:
            column_name, column_type = definition.split(" ", maxsplit=1)
            result_columns.append(column_name)
            column_types.append(column_type)
    for row in records:
        where = column_value_to_where(column, row[column], quote=quote_column)
        for (
            result_column,
            column_type,
            key,
        ) in zip(result_columns, column_types, select_columns):
            updates.append(
                {
                    "column": result_column,
                    "type": column_type,
                    "value": row[key],
                    "where": where,
                }
            )
    return updates, add_columns


def update_columns(output_name, output_layer, updates, add_columns):
    """Update attribute values based on a list of updates"""
    if add_columns:
        gs.run_command(
            "v.db.addcolumn",
            map=output_name,
            layer=output_layer,
            columns=",".join(add_columns),
        )
    db_info = gs.vector_db(output_name)[int(output_layer)]
    sql = updates_to_sql(table=db_info["table"], updates=updates)
    gs.write_command(
        "db.execute",
        input="-",
        database=db_info["database"],
        driver=db_info["driver"],
        stdin=sql,
    )


def statistics_to_one_vector(
    input_vector, dissolve_column, columns_to_aggregate, result_columns, output
):
    updates, add_columns = aggregate_attributes_sql(
        input_name=input_vector,
        input_layer=1,
        column=dissolve_column,
        quote_column=True,
        columns_to_aggregate=columns_to_aggregate,
        methods=None,
        result_columns=result_columns,
    )
    update_columns(
        output_name=output,
        output_layer=1,
        updates=updates,
        add_columns=add_columns,
    )
