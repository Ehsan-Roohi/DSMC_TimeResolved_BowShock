#!/usr/bin/env python3
"""Generate the three immutable Gate 1C OpenFOAM-v2312 cases."""

from __future__ import annotations

import argparse
from pathlib import Path


LENGTH = 0.1
FULL_HEIGHT = 0.05
INTERFACE_HEIGHT = 0.015
HALF_SPAN = 0.00125
U_INF = 1500.0
T_INF = 300.0
T_WALL = 550.0
N_INF = 1.0e20
P_INF = 0.4141947
KINETIC_DT = 2.5e-7
KINETIC_STEPS = 1600


def header(field_class: str, object_name: str, location: str | None = None) -> str:
    location_line = f'    location    "{location}";\n' if location else ""
    return f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       {field_class};
{location_line}    object      {object_name};
}}

"""


def write(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")


def block_mesh(height: float, nx: int, ny: int, top_name: str) -> str:
    return header("dictionary", "blockMeshDict", "system") + f"""vertices
(
    (0      0       {-HALF_SPAN})
    ({LENGTH} 0       {-HALF_SPAN})
    ({LENGTH} {height} {-HALF_SPAN})
    (0      {height} {-HALF_SPAN})
    (0      0        {HALF_SPAN})
    ({LENGTH} 0        {HALF_SPAN})
    ({LENGTH} {height}  {HALF_SPAN})
    (0      {height}  {HALF_SPAN})
);

blocks
(
    hex (0 1 2 3 4 5 6 7) ({nx} {ny} 1) simpleGrading (1 1 1)
);

boundary
(
    inlet
    {{
        type patch;
        faces ((0 4 7 3));
    }}
    outlet
    {{
        type patch;
        faces ((1 2 6 5));
    }}
    plate
    {{
        type wall;
        faces ((0 1 5 4));
    }}
    {top_name}
    {{
        type patch;
        faces ((3 7 6 2));
    }}
    frontAndBack
    {{
        type empty;
        faces ((0 3 2 1) (4 5 6 7));
    }}
);
"""


def continuum_field(
    name: str,
    field_class: str,
    dimensions: str,
    internal: str,
    inlet: str,
    outlet: str,
    plate: str,
    farfield: str,
) -> str:
    return header(field_class, name, "0") + f"""dimensions      {dimensions};
internalField   uniform {internal};

boundaryField
{{
    inlet
    {{
        type fixedValue;
        value uniform {inlet};
    }}
    outlet
    {{
        type zeroGradient;
    }}
    plate
    {{
        {plate}
    }}
    farfield
    {{
        type fixedValue;
        value uniform {farfield};
    }}
    frontAndBack
    {{
        type empty;
    }}
}}
"""


def make_continuum(case: Path) -> None:
    write(case / "system/blockMeshDict", block_mesh(FULL_HEIGHT, 80, 40, "farfield"))
    write(
        case / "0/p",
        continuum_field(
            "p", "volScalarField", "[1 -1 -2 0 0 0 0]", str(P_INF),
            str(P_INF), str(P_INF), "type zeroGradient;", str(P_INF),
        ),
    )
    write(
        case / "0/T",
        continuum_field(
            "T", "volScalarField", "[0 0 0 1 0 0 0]", str(T_INF),
            str(T_INF), str(T_INF),
            f"type fixedValue; value uniform {T_WALL};", str(T_INF),
        ),
    )
    write(
        case / "0/U",
        continuum_field(
            "U", "volVectorField", "[0 1 -1 0 0 0 0]", f"({U_INF} 0 0)",
            f"({U_INF} 0 0)", f"({U_INF} 0 0)",
            "type noSlip;", f"({U_INF} 0 0)",
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
    specie
    {
        molWeight   39.948;
    }
    thermodynamics
    {
        Cp          520.330343080582;
        Hf          0;
    }
    transport
    {
        mu          2.23e-5;
        Pr          0.666666666666667;
    }
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
deltaT              2.5e-8;
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
divSchemes
{
    default none;
    div(tauMC) Gauss linear;
}
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
    "(rho|rhoU|rhoE)"
    {
        solver diagonal;
    }
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


def kinetic_boundary(top_name: str, kind: str) -> str:
    open_names = ("inlet", "outlet", top_name)
    parts: list[str] = ["boundaryField\n{\n"]
    for patch in open_names:
        if kind == "temperature":
            body = f"type fixedValue; value uniform {T_INF};"
        elif kind == "velocity":
            body = f"type fixedValue; value uniform ({U_INF} 0 0);"
        else:
            body = "type zeroGradient;"
        parts.append(f"    {patch}\n    {{ {body} }}\n")
    if kind == "temperature":
        plate = f"type fixedValue; value uniform {T_WALL};"
    elif kind == "velocity":
        plate = "type noSlip;"
    elif kind == "vector_observable":
        plate = "type calculated; value uniform (0 0 0);"
    else:
        plate = "type calculated; value uniform 0;"
    parts.append(f"    plate\n    {{ {plate} }}\n")
    parts.append("    frontAndBack\n    { type empty; }\n}\n")
    return "".join(parts)


def kinetic_field(
    case: Path,
    name: str,
    field_class: str,
    dimensions: str,
    internal: str,
    top_name: str,
    kind: str,
) -> None:
    write(
        case / f"0/{name}",
        header(field_class, name, "0")
        + f"dimensions      {dimensions};\n"
        + f"internalField   uniform {internal};\n\n"
        + kinetic_boundary(top_name, kind),
    )


def make_kinetic(case: Path, height: float, ny: int, top_name: str, hybrid: bool) -> None:
    write(case / "system/blockMeshDict", block_mesh(height, 40, ny, top_name))
    kinetic_field(
        case, "boundaryT", "volScalarField", "[0 0 0 1 0 0 0]",
        str(T_INF), top_name, "temperature",
    )
    kinetic_field(
        case, "boundaryU", "volVectorField", "[0 1 -1 0 0 0 0]",
        f"({U_INF} 0 0)", top_name, "velocity",
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
        kinetic_field(case, name, field_class, dimensions, internal, top_name, kind)

    inflow = "InflowBoundaryModel none;\n" if hybrid else f"""InflowBoundaryModel FreeStream;
FreeStreamCoeffs
{{
    numberDensities
    {{
        Ar {N_INF};
    }}
}}
"""
    write(
        case / "constant/dsmcProperties",
        header("dictionary", "dsmcProperties", "constant")
        + f"""nEquivalentParticles 4e10;

WallInteractionModel MaxwellianThermal;

BinaryCollisionModel VariableHardSphere;
VariableHardSphereCoeffs
{{
    Tref 273;
}}

{inflow}
typeIdList (Ar);
moleculeProperties
{{
    Ar
    {{
        mass                        6.6335209e-26;
        diameter                    4.17e-10;
        internalDegreesOfFreedom    0;
        omega                       0.81;
    }}
}}
""",
    )
    write(
        case / "system/dsmcInitialiseDict",
        header("dictionary", "dsmcInitialiseDict", "system")
        + f"""numberDensities
{{
    Ar {N_INF};
}}
temperature {T_INF};
velocity ({U_INF} 0 0);
""",
    )
    write(
        case / "system/controlDict",
        header("dictionary", "controlDict", "system")
        + f"""application         dsmcFoamGate1C;
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
    make_kinetic(root / "hybrid", INTERFACE_HEIGHT, 6, "interface", True)
    make_kinetic(root / "reference", FULL_HEIGHT, 20, "farfield", False)
    print(f"GATE1C_CASES={root}")


if __name__ == "__main__":
    main()
