"""Raw sensor negative-reading policy, applied before averaging and conversion."""
SIDEFLOW_COLUMN = 'Sumo__Plant__Sideflowdivider3__param__Qpumped_target'
SIDEFLOW_NEGATIVE_VALUE = 0.001


def negative_replacement(column):
    return SIDEFLOW_NEGATIVE_VALUE if column == SIDEFLOW_COLUMN else 0.0


def normalize_reading(column, value):
    return negative_replacement(column) if value < 0 else value


def negative_details(column):
    replacement = negative_replacement(column)
    return dict(treatment='negative_to_minimum' if replacement else 'negative_to_zero',
                replacement_raw_value=replacement)
