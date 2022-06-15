#!/usr/bin/env python3

# %module
# % description: Delineates sewershed from census blocks and adds population information
# % keyword: vector
# % keyword: dissolve
# % keyword: area
# % keyword: line
# %end
# %option G_OPT_V_INPUT
# % label: Network (lines) or sewershed (areas, polygons)
# % key: sewer
# %end
# %option G_OPT_V_FIELD
# % key: sewer_layer
# %end
# %option G_OPT_V_INPUT
# % label: US Census blocks
# % key: census_blocks
# %end
# %option G_OPT_V_FIELD
# % key: census_blocks_layer
# %end
# %option G_OPT_V_OUTPUT
# %end
# %option G_OPT_DB_COLUMN
# % key: sewer_select_column
# % description: Attribute column to select sewer features by
# %end
# %option
# % key: sewer_select_value
# % description: Attribute value to select sewer features by
# %end

"""Sewershed delineation tool which runs in GRASS GIS"""

import atexit
import subprocess

import grass.script as gs


def get_columns():
    """Return aggregate column expressions and result column definitions"""
    # Selected columns in US census blocks.
    total_population_name = "P0010001"
    population_columns = [
        ("race_white", "P0010003"),
        ("race_black_or_african_american", "P0010004"),
        ("race_american_indian_or_alaska_native", "P0010005"),
        ("race_asian", "P0010006"),
        ("race_native_hawaiian_and_other_pacific_islander", "P0010007"),
        ("race_some_other_race", "P0010008"),
        ("hispanic_or_latino", "P0020002"),
        ("population_18_years_and_over", "P0030001"),
        ("housing_units_total", "H0010001"),
        ("housing_occupied", "H0010002"),
        ("housing_vacant", "H0010003"),
        ("quarters_total", "P0050001"),
        ("quarters_correctional_facilities_for_adults", "P0050003"),
        ("quarters_nursing_facilities", "P0050005"),
        ("quarters_college_university_student_housing", "P0050008"),
        ("quarters_military_quarters", "P0050009"),
    ]
    # Create columns and expressions.
    aggregate_columns = [f"sum({total_population_name})"]
    result_columns = ["total_population integer"]
    float_type = "real"
    for result_name, reference_name in population_columns:
        # Create expression sum(a) / sum(b).
        aggregate_columns.append(
            f"cast(sum({reference_name}) as {float_type}) "
            f"/ sum({total_population_name})"
        )
        result_columns.append(f"{result_name} {float_type}")
    return aggregate_columns, result_columns


def cleanup(name):
    """Remove temporary vector silently"""
    gs.run_command(
        "g.remove",
        flags="f",
        type="vector",
        name=name,
        quiet=True,
        stderr=subprocess.DEVNULL,
    )


def main():
    """Process command line parameters and perform the delineation"""
    options, unused_flags = gs.parser()

    sewer_vector = options["sewer"]
    sewer_layer = options["sewer_layer"]
    census_blocks_vector = options["census_blocks"]
    census_blocks_layer = options["census_blocks_layer"]
    output = options["output"]

    sewer_select_column = options["sewer_select_column"]
    sewer_select_value = options["sewer_select_value"]

    # Dissolving is done based on the values in this column.
    dissolve_column = "State_Name"  # from US census data

    sewershed_blocks = gs.append_node_pid("tmp_blocks")
    atexit.register(cleanup, sewershed_blocks)

    if sewer_select_column:
        # Decide if the value needs quoting.
        try:
            float(sewer_select_value)
        except ValueError:
            sewer_select_value = f"'{sewer_select_value}'"

        sewershed_selection_vector = gs.append_node_pid("tmp_selection")
        atexit.register(cleanup, sewershed_selection_vector)

        # Select only relevant part of the sewer network.
        gs.run_command(
            "v.extract",
            input=sewer_vector,
            layer=sewer_layer,
            output=sewershed_selection_vector,
            where=f"{sewer_select_column} = {sewer_select_value}",
        )
        sewershed_selection_layer = 1
    else:
        # Using the input as is.
        sewershed_selection_vector = sewer_vector
        sewershed_selection_layer = sewer_layer

    # Select only census blocks which overlap with the sewer network.
    gs.run_command(
        "v.select",
        ainput=census_blocks_vector,
        alayer=census_blocks_layer,
        atype="area",
        binput=sewershed_selection_vector,
        blayer=sewershed_selection_layer,
        output=sewershed_blocks,
        operator="intersects",
    )
    # Dissolve selected blocks and compute aggregate statistics.
    aggregate_columns, result_columns = get_columns()
    gs.run_command(
        "v.dissolve",
        input=sewershed_blocks,
        column=dissolve_column,
        output=output,
        aggregate_column=aggregate_columns,
        result_column=result_columns,
    )
    gs.vector_history(output)


if __name__ == "__main__":
    main()
