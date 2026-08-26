#!/usr/bin/env python3
"""Generate the immutable Gate 3C annular cylinder cases for OpenFOAM-v2312."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from generate_gate1c_cases import header, write


R_CYLINDER = 0.01
R_INTERFACE = 0.025
R_OUTER = 0.05
HALF_SPAN = 0.00125
ANGULAR_CELLS = 64
SECTORS = 8
U_INF = 1500.0
T_INF = 300.0
T_WALL = 550.0
N_INF = 1.0e20
P_INF = 0.4141947
KINETIC_DT = 2.5e-7
KINETIC_STEPS = 1600


def point(radius: float, angle: float, z: float) -> tuple[float, float, float]:
    return radius * math.cos(angle), radius * math.sin(angle), z


def fmt_point(value: tuple[float, float, float]) -> str:
    return "(" + " ".join(f"{component:.16g}" for component in value) + ")"


def vertex_index(z_layer: int, ring: int, sector: int) -> int:
    return z_layer * (2 * SECTORS) + ring * SECTORS + sector % SECTORS


def ring_block_mesh(
    inner_radius: float,
    outer_radius: float,
    radial_cells: int,
    inner_name: str,
    outer_mode: str,
) -> str:
    if ANGULAR_CELLS % SECTORS:
        raise ValueError("angular cell count must be divisible by sector count")
    vertices: list[str] = []
    for z in (-HALF_SPAN, HALF_SPAN):
        for radius in (inner_radius, outer_radius):
            for sector in range(SECTORS):
                vertices.append(
                    "    " + fmt_point(point(radius, 2.0 * math.pi * sector / SECTORS, z))
                )

    blocks: list[str] = []
    angular_per_sector = ANGULAR_CELLS // SECTORS
    for sector in range(SECTORS):
        next_sector = (sector + 1) % SECTORS
        indices = (
            vertex_index(0, 0, sector),
            vertex_index(0, 1, sector),
            vertex_index(0, 1, next_sector),
            vertex_index(0, 0, next_sector),
            vertex_index(1, 0, sector),
            vertex_index(1, 1, sector),
            vertex_index(1, 1, next_sector),
            vertex_index(1, 0, next_sector),
        )
        blocks.append(
            "    hex ({} ) ({} {} 1) simpleGrading (1 1 1)".format(
                " ".join(map(str, indices)), radial_cells, angular_per_sector
            )
        )

    edges: list[str] = []
    for z_layer, z in enumerate((-HALF_SPAN, HALF_SPAN)):
        for ring, radius in enumerate((inner_radius, outer_radius)):
            for sector in range(SECTORS):
                next_sector = (sector + 1) % SECTORS
                mid_angle = 2.0 * math.pi * (sector + 0.5) / SECTORS
                edges.append(
                    "    arc {} {} {}".format(
                        vertex_index(z_layer, ring, sector),
                        vertex_index(z_layer, ring, next_sector),
                        fmt_point(point(radius, mid_angle, z)),
                    )
                )

    inner_faces: list[str] = []
    outer_faces: dict[str, list[str]] = {
        "farfieldInlet": [],
        "farfieldOutlet": [],
        "interface": [],
    }
    front_back: list[str] = []
    for sector in range(SECTORS):
        next_sector = (sector + 1) % SECTORS
        i0 = vertex_index(0, 0, sector)
        i1 = vertex_index(0, 0, next_sector)
        o0 = vertex_index(0, 1, sector)
        o1 = vertex_index(0, 1, next_sector)
        ib0 = vertex_index(1, 0, sector)
        ib1 = vertex_index(1, 0, next_sector)
        ob0 = vertex_index(1, 1, sector)
        ob1 = vertex_index(1, 1, next_sector)
        inner_faces.append(f"            ({i0} {ib0} {ib1} {i1})")
        outer_face = f"            ({o0} {o1} {ob1} {ob0})"
        if outer_mode == "interface":
            outer_faces["interface"].append(outer_face)
        elif sector in (2, 3, 4, 5):
            outer_faces["farfieldInlet"].append(outer_face)
        else:
            outer_faces["farfieldOutlet"].append(outer_face)
        front_back.extend(
            [
                f"            ({i0} {o0} {o1} {i1})",
                f"            ({ib0} {ib1} {ob1} {ob0})",
            ]
        )

    patches = [
        f"""    {inner_name}
    {{
        type wall;
        faces
        (
{chr(10).join(inner_faces)}
        );
    }}"""
    ]
    if outer_mode == "interface":
        patches.append(
            f"""    interface
    {{
        type patch;
        faces
        (
{chr(10).join(outer_faces['interface'])}
        );
    }}"""
        )
    else:
        for patch_name in ("farfieldInlet", "farfieldOutlet"):
            patches.append(
                f"""    {patch_name}
    {{
        type patch;
        faces
        (
{chr(10).join(outer_faces[patch_name])}
        );
    }}"""
            )
    patches.append(
        f"""    frontAndBack
    {{
        type empty;
        faces
        (
{chr(10).join(front_back)}
        );
    }}"""
    )

    return header("dictionary", "blockMeshDict", "system") + f"""vertices
(
{chr(10).join(vertices)}
);

blocks
(
{chr(10).join(blocks)}
);

edges
(
{chr(10).join(edges)}
);

boundary
(
{chr(10).join(patches)}
);
"""


def continuum_field(
    name: str,
    field_class: str,
    dimensions: str,
    internal: str,
    inlet: str,
    cylinder_body: str,
) -> str:
    return header(field_class, name, "0") + f"""dimensions      {dimensions};
internalField   uniform {internal};

boundaryField
{{
    cylinder
    {{
        {cylinder_body}
    }}
    farfieldInlet
    {{
        type fixedValue;
        value uniform {inlet};
    }}
    farfieldOutlet
    {{
        type zeroGradient;
    }}
    frontAndBack
    {{
        type empty;
    }}
}}
"""


def make_continuum(case: Path) -> None:
    write(
        case / "system/blockMeshDict",
        ring_block_mesh(R_CYLINDER, R_OUTER, 32, "cylinder", "farfield"),
    )
    write(
        case / "0/p",
        continuum_field(
            "p", "volScalarField", "[1 -1 -2 0 0 0 0]", str(P_INF),
            str(P_INF), "type zeroGradient;",
        ),
    )
    write(
        case / "0/T",
        continuum_field(
            "T", "volScalarField", "[0 0 0 1 0 0 0]", str(T_INF),
            str(T_INF), f"type fixedValue; value uniform {T_WALL};",
        ),
    )
    write(
        case / "0/U",
        continuum_field(
            "U", "volVectorField", "[0 1 -1 0 0 0 0]", f"({U_INF} 0 0)",
            f"({U_INF} 0 0)", "type noSlip;",
        ),
    )
    write(
        case / "constant/thermophysicalProperties",
        header("dictionary", "thermophysicalProperties", "constant")
        + """thermoType
{
    type            hePsiThermo;
    mixture         pureMixture;
    transport       const;
    thermo          hConst;
    equationOfState perfectGas;
    specie          specie;
    energy          sensibleInternalEnergy;
}

mixture
{
    specie { molWeight 39.948; }
    thermodynamics { Cp 520.330343080582; Hf 0; }
    transport { mu 2.23e-5; Pr 0.666666666666667; }
}
""",
    )
    for dictionary_name in ("momentumTransport", "turbulenceProperties"):
        write(
            case / f"constant/{dictionary_name}",
            header("dictionary", dictionary_name, "constant")
            + "simulationType laminar;\n",
        )
    write(
        case / "system/controlDict",
        header("dictionary", "controlDict", "system")
        + """application         rhoCentralFoam;
startFrom           startTime;
startTime           0;
stopAt              endTime;
endTime             1e-4;
deltaT              1e-8;
writeControl        runTime;
writeInterval       2.5e-5;
purgeWrite          2;
writeFormat         ascii;
writePrecision      12;
writeCompression    off;
timeFormat          general;
timePrecision       10;
runTimeModifiable   false;
adjustTimeStep      yes;
maxCo               0.2;
maxDeltaT           1e-7;
""",
    )
    write(
        case / "system/fvSchemes",
        header("dictionary", "fvSchemes", "system")
        + """fluxScheme Kurganov;
ddtSchemes { default Euler; }
gradSchemes { default Gauss linear; }
divSchemes { default none; div(tauMC) Gauss linear; }
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes
{
    default linear;
    reconstruct(rho) vanLeer;
    reconstruct(U) vanLeerV;
    reconstruct(T) vanLeer;
}
snGradSchemes { default corrected; }
wallDist { method meshWave; }
""",
    )
    write(
        case / "system/fvSolution",
        header("dictionary", "fvSolution", "system")
        + """solvers
{
    "(rho|rhoU|rhoE)" { solver diagonal; }
    "(U|e)"
    {
        solver smoothSolver;
        smoother symGaussSeidel;
        tolerance 1e-10;
        relTol 0;
    }
}
""",
    )


def kinetic_boundary(open_patches: tuple[str, ...], kind: str) -> str:
    parts = ["boundaryField\n{\n"]
    for patch in open_patches:
        if kind == "temperature":
            body = f"type fixedValue; value uniform {T_INF};"
        elif kind == "velocity":
            body = f"type fixedValue; value uniform ({U_INF} 0 0);"
        else:
            body = "type zeroGradient;"
        parts.append(f"    {patch}\n    {{ {body} }}\n")
    if kind == "temperature":
        cylinder = f"type fixedValue; value uniform {T_WALL};"
    elif kind == "velocity":
        cylinder = "type noSlip;"
    elif kind == "vector_observable":
        cylinder = "type calculated; value uniform (0 0 0);"
    else:
        cylinder = "type calculated; value uniform 0;"
    parts.append(f"    cylinder\n    {{ {cylinder} }}\n")
    parts.append("    frontAndBack\n    { type empty; }\n}\n")
    return "".join(parts)


def kinetic_field(
    case: Path,
    name: str,
    field_class: str,
    dimensions: str,
    internal: str,
    open_patches: tuple[str, ...],
    kind: str,
) -> None:
    write(
        case / f"0/{name}",
        header(field_class, name, "0")
        + f"dimensions      {dimensions};\n"
        + f"internalField   uniform {internal};\n\n"
        + kinetic_boundary(open_patches, kind),
    )


def make_kinetic(case: Path, hybrid: bool) -> None:
    if hybrid:
        outer_radius = R_INTERFACE
        radial_cells = 6
        open_patches = ("interface",)
        outer_mode = "interface"
    else:
        outer_radius = R_OUTER
        radial_cells = 16
        open_patches = ("farfieldInlet", "farfieldOutlet")
        outer_mode = "farfield"
    write(
        case / "system/blockMeshDict",
        ring_block_mesh(R_CYLINDER, outer_radius, radial_cells, "cylinder", outer_mode),
    )
    kinetic_field(
        case, "boundaryT", "volScalarField", "[0 0 0 1 0 0 0]",
        str(T_INF), open_patches, "temperature",
    )
    kinetic_field(
        case, "boundaryU", "volVectorField", "[0 1 -1 0 0 0 0]",
        f"({U_INF} 0 0)", open_patches, "velocity",
    )
    fields = (
        ("q", "volScalarField", "[1 0 -3 0 0 0 0]", "0", "scalar_observable"),
        ("fD", "volVectorField", "[1 -1 -2 0 0 0 0]", "(0 0 0)", "vector_observable"),
        ("rhoN", "volScalarField", "[0 -3 0 0 0 0 0]", "0", "scalar_observable"),
        ("rhoM", "volScalarField", "[1 -3 0 0 0 0 0]", "0", "scalar_observable"),
        ("dsmcRhoN", "volScalarField", "[0 -3 0 0 0 0 0]", "0", "scalar_observable"),
        ("linearKE", "volScalarField", "[1 -1 -2 0 0 0 0]", "0", "scalar_observable"),
        ("internalE", "volScalarField", "[1 -1 -2 0 0 0 0]", "0", "scalar_observable"),
        ("iDof", "volScalarField", "[0 -3 0 0 0 0 0]", "0", "scalar_observable"),
        ("momentum", "volVectorField", "[1 -2 -1 0 0 0 0]", "(0 0 0)", "vector_observable"),
    )
    for name, field_class, dimensions, internal, kind in fields:
        kinetic_field(case, name, field_class, dimensions, internal, open_patches, kind)

    inflow = "InflowBoundaryModel none;\n" if hybrid else f"""InflowBoundaryModel FreeStream;
FreeStreamCoeffs
{{
    numberDensities {{ Ar {N_INF}; }}
}}
"""
    write(
        case / "constant/dsmcProperties",
        header("dictionary", "dsmcProperties", "constant")
        + f"""nEquivalentParticles 4e10;
WallInteractionModel MaxwellianThermal;
BinaryCollisionModel VariableHardSphere;
VariableHardSphereCoeffs {{ Tref 273; }}
{inflow}
typeIdList (Ar);
moleculeProperties
{{
    Ar
    {{
        mass 6.6335209e-26;
        diameter 4.17e-10;
        internalDegreesOfFreedom 0;
        omega 0.81;
    }}
}}
""",
    )
    write(
        case / "system/dsmcInitialiseDict",
        header("dictionary", "dsmcInitialiseDict", "system")
        + f"""numberDensities {{ Ar {N_INF}; }}
temperature {T_INF};
velocity ({U_INF} 0 0);
""",
    )
    write(
        case / "system/controlDict",
        header("dictionary", "controlDict", "system")
        + f"""application         dsmcFoamGate3C;
startFrom           startTime;
startTime           0;
stopAt              endTime;
endTime             {KINETIC_DT * KINETIC_STEPS:.12g};
deltaT              {KINETIC_DT};
writeControl        timeStep;
writeInterval       400;
purgeWrite          1;
writeFormat         ascii;
writePrecision      12;
writeCompression    off;
timeFormat          general;
timePrecision       10;
runTimeModifiable   false;
""",
    )
    write(
        case / "system/fvSchemes",
        header("dictionary", "fvSchemes", "system")
        + """ddtSchemes { default Euler; }
gradSchemes { default Gauss linear; }
divSchemes { default none; }
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes { default corrected; }
""",
    )
    write(
        case / "system/fvSolution",
        header("dictionary", "fvSolution", "system") + "solvers {}\n",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_directory", type=Path)
    args = parser.parse_args()
    root = args.run_directory.resolve()
    if root.exists():
        raise SystemExit(f"refusing to overwrite existing run directory: {root}")
    root.mkdir(parents=True)
    make_continuum(root / "continuum")
    make_kinetic(root / "hybrid", True)
    make_kinetic(root / "reference", False)
    print(f"GATE3C_CASES={root}")


if __name__ == "__main__":
    main()
