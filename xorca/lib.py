"""Library for the conversion from NEMO output to XGCM data sets."""

import numpy as np
import xarray as xr

from . import orca_names


def trim_and_squeeze(ds):
    """Remove redundant grid points and drop singleton dimensions."""
    if "y" in ds.dims:
        ds = ds.isel(y=slice(1, -1))
    if "x" in ds.dims:
        ds = ds.isel(x=slice(1, -1))
    ds = ds.squeeze()
    return ds


def create_minimal_coords_ds(ds_mm):
    """Create a minimal set of coordinates from a mesh-mask dataset.

    This creates `"central"` and `"right"` grid points for the horizontal grid
    and `"central"` and `"left"` grid points in the vertical.

    """
    N_z = len(ds_mm.coords["z"])
    N_y = len(ds_mm.coords["y"])
    N_x = len(ds_mm.coords["x"])

    coords = {
        "z_c": (["z_c", ], np.arange(1, N_z + 1),
                {"axis": "Z"}),
        "z_l": (["z_l", ], np.arange(1, N_z + 1) - 0.5,
                {"axis": "Z", "c_grid_axis_shift": - 0.5}),
        "y_c": (["y_c", ], np.arange(1, N_y + 1),
                {"axis": "Y"}),
        "y_r": (["y_r", ], np.arange(1, N_y + 1) + 0.5,
                {"axis": "Y", "c_grid_axis_shift": 0.5}),
        "x_c": (["x_c", ], np.arange(1, N_x + 1),
                {"axis": "X"}),
        "x_r": (["x_r", ], np.arange(1, N_x + 1) + 0.5,
                {"axis": "X", "c_grid_axis_shift": 0.5})
    }

    return xr.Dataset(coords=coords)


def copy_coords(return_ds, ds_in):
    """Copy coordinates and map them to the correct grid.

    This copies all coordinates defined in `xorca.orca_names.orca_coords` from
    `ds_in` to `return_ds`.
    """
    for key, names in orca_names.orca_coords.items():
        new_name = key
        new_dims = names["dims"]
        old_name = names.get("old_name", new_name)
        if old_name in ds_in.coords:
            return_ds.coords[new_name] = (new_dims,
                                          ds_in.coords[old_name].data)
        if old_name in ds_in:
            return_ds.coords[new_name] = (new_dims,
                                          ds_in[old_name].data)
    return return_ds


def copy_vars(return_ds, raw_ds):
    """Copy variables and map them to the correct grid.

    This copies all variables defined in `xorca.orca_names.orca_variables` from
    `raw_ds` to `return_ds`.
    """
    for key, names in orca_names.orca_variables.items():
        new_name = key
        new_dims = names["dims"]
        old_name = names.get("old_name", new_name)
        if old_name in raw_ds:
            return_ds[new_name] = (new_dims, raw_ds[old_name].data)
    return return_ds


def rename_dims(ds):
    """Rename dimensions.

    This renames all dimensions defined in `xorca.orca_names.rename_dims` and
    returns the data set with renamed dimensinos.
    """
    rename_dict = {
        k: v for k, v in orca_names.rename_dims.items()
        if k in ds.dims
    }
    return ds.rename(rename_dict)


def force_sign_of_coordinate(ds):
    """Force definite sign of coordinates.

    For all coordinates defined in `xorca.orca_names.orca_coordinates`, enforce
    a sign if there is an item telling us to do so.  This is most useful to
    ensure that, e.g., depth is _always_ pointing upwards or downwards.
    """
    for k, v in orca_names.orca_coords.items():
        force_sign = v.get("force_sign", False)
        if force_sign and k in ds.coords:
            ds[k] = force_sign * abs(ds[k])

    return ds


def _open_mm_dataset(mm_files):
    """Open mm_files as either a multi-file or a single file xarray Dataset."""
    try:
        ds_mm = xr.open_mfdataset(mm_files)
    except TypeError as e:
        ds_mm = xr.open_dataset(mm_files)

    return ds_mm


def preprocess_orca(mm_files, ds):
    """Preprocess orca datasets before concatenating.

    This is meant to be used like:
    ```python
    ds = xr.open_mfdataset(
        data_files,
        preprocess=(lambda ds:
                    preprocess_orca(mesh_mask_files, ds)))
    ```

    Parameters
    ----------
    mm_files : Path | sequence | string
        Anything accepted by `xr.open_mfdataset` or, `xr.open_dataset`: A
        single file name, a sequence of Paths or file names, a glob statement.
    ds : xarray dataset
        Xarray dataset to be processed before concatenating.

    Returns
    -------
    xarray dataset

    """
    # construct minimal grid-aware data set from mesh-mask files
    ds_mm = _open_mm_dataset(mm_files)
    ds_mm = trim_and_squeeze(ds_mm)
    return_ds = create_minimal_coords_ds(ds_mm)

    # make sure dims are called correctly and trim input ds
    ds = rename_dims(ds)
    ds = trim_and_squeeze(ds)

    # copy coordinates from the mesh-mask and from the data set
    return_ds = copy_coords(return_ds, ds_mm)
    return_ds = copy_coords(return_ds, ds)

    # copy variables from the data set
    return_ds = copy_vars(return_ds, ds)

    # Finally, make sure depth is positive upward
    return_ds = force_sign_of_coordinate(return_ds)

    return return_ds
