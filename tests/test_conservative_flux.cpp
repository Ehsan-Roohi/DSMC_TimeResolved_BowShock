// SPDX-License-Identifier: GPL-3.0-or-later
#include "muiFoam/ConservativeFlux.hpp"

#include <cassert>
#include <cstdio>
#include <stdexcept>
#include <vector>

int main()
{
    using muiFoam::ConservativeFlux;

    assert(!muiFoam::statisticallyResolved(32, 0.01));
    assert(!muiFoam::statisticallyResolved(256, 0.08));
    assert(muiFoam::statisticallyResolved(256, 0.03));

    ConservativeFlux oldFlux = {{1.0, 2.0, 3.0, 4.0, 5.0}};
    ConservativeFlux newFlux = {{3.0, 4.0, 5.0, 6.0, 7.0}};
    const ConservativeFlux relaxed =
        muiFoam::relaxedFlux(oldFlux, newFlux, 0.25);
    const ConservativeFlux expected = {{1.5, 2.5, 3.5, 4.5, 5.5}};
    assert(muiFoam::maximumRelativeDifference(relaxed, expected) < 1.0e-15);

    std::vector<ConservativeFlux> faces(2);
    faces[0] = oldFlux;
    faces[1] = newFlux;
    const ConservativeFlux total = muiFoam::totalFlux(faces);
    const ConservativeFlux expectedTotal = {{4.0, 6.0, 8.0, 10.0, 12.0}};
    assert(muiFoam::maximumRelativeDifference(total, expectedTotal) < 1.0e-15);

    std::vector<ConservativeFlux> mapped(3);
    mapped[0] = {{0.8, 1.7, 2.6, 3.5, 4.4}};
    mapped[1] = {{1.2, 2.0, 2.8, 3.6, 4.4}};
    mapped[2] = {{1.7, 2.0, 2.7, 3.4, 4.1}};
    const std::vector<double> targetAreas = {1.0, 2.0, 1.0};
    const double rawProjectionError = muiFoam::projectGlobalConservation
    (
        mapped,
        expectedTotal,
        targetAreas
    );
    assert(rawProjectionError > 0.0);
    assert
    (
        muiFoam::maximumRelativeDifference
        (
            muiFoam::totalFlux(mapped),
            expectedTotal
        ) < 1.0e-15
    );

    bool rejectedBadAreas = false;
    try
    {
        std::vector<double> badAreas = {1.0, 0.0, 1.0};
        (void)muiFoam::projectGlobalConservation
        (
            mapped,
            expectedTotal,
            badAreas
        );
    }
    catch (const std::runtime_error&)
    {
        rejectedBadAreas = true;
    }
    assert(rejectedBadAreas);

    const char* restartPath = "gate3a_flux_restart_test.dat";
    muiFoam::writeFluxRestart(restartPath, 7, faces);
    const muiFoam::FluxRestart restored =
        muiFoam::readFluxRestart(restartPath, faces.size());
    assert(restored.lastWindow == 7);
    assert(restored.faces.size() == faces.size());
    for (std::size_t face = 0; face < faces.size(); ++face)
    {
        assert
        (
            muiFoam::maximumRelativeDifference(restored.faces[face], faces[face])
          < 1.0e-15
        );
    }
    std::remove(restartPath);

    bool rejectedWrongCount = false;
    muiFoam::writeFluxRestart(restartPath, 1, faces);
    try
    {
        (void)muiFoam::readFluxRestart(restartPath, faces.size() + 1);
    }
    catch (const std::runtime_error&)
    {
        rejectedWrongCount = true;
    }
    std::remove(restartPath);
    assert(rejectedWrongCount);
    return 0;
}
