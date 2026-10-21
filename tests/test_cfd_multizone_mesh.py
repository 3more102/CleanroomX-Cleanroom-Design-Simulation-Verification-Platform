"""Synthetic mesh-selection contracts only; no artificial CFD evidence."""
import pytest

vtk = pytest.importorskip("vtk")

from cleanroomx.cfd_multizone_mesh import recorded_mesh_edge_actor
from test_cfd_multizone_vtk import _source


def test_original_cell_selection_maps_exact_mesh_ids_without_adding_cells():
    image = vtk.vtkImageData()
    image.SetDimensions(4, 2, 2)
    image.SetSpacing(1, 1, 1)
    append = vtk.vtkAppendFilter()
    append.AddInputData(image)
    append.Update()
    mesh = append.GetOutput()
    actor = recorded_mesh_edge_actor(mesh, _source(), plane_axis="x", plane_position_m=1.5)
    mapper = actor.GetMapper()
    mapper.Update()
    assert mapper.GetInput().GetNumberOfLines() == 12
    assert mapper.GetInput().GetBounds() == pytest.approx((1., 2., 0., 1., 0., 1.))
    assert not mapper.GetScalarVisibility()
    assert mesh.GetNumberOfCells() == 3
    with pytest.raises(ValueError, match="No computed cells"):
        recorded_mesh_edge_actor(mesh, _source(), plane_axis="x", plane_position_m=99.)
    with pytest.raises(ValueError, match="cell count"):
        recorded_mesh_edge_actor(vtk.vtkUnstructuredGrid(), _source())
