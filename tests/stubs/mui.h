#ifndef GATE3D_TEST_STUB_MUI_H
#define GATE3D_TEST_STUB_MUI_H

#include <cstddef>
#include <string>

namespace mui
{

template<std::size_t Dimension>
class point
{
public:
    double& operator[](const std::size_t index) { return values_[index]; }
    const double& operator[](const std::size_t index) const { return values_[index]; }

private:
    double values_[Dimension] = {};
};

using point2d = point<2>;
using point3d = point<3>;

template<typename T>
class sampler_exact2d
{
};

class temporal_sampler_exact2d
{
};

template<typename T>
class sampler_exact3d
{
};

class temporal_sampler_exact3d
{
};

template<typename T>
class uniface
{
};

class uniface2d
{
public:
    explicit uniface2d(const std::string&) {}

    void push(const std::string&, const point2d&, const double) {}
    void commit(const int) {}

    template<typename Spatial, typename Temporal>
    double fetch
    (
        const std::string&, const point2d&, const int,
        Spatial&, Temporal&
    )
    {
        return 0.0;
    }
};

class uniface3d
{
public:
    explicit uniface3d(const std::string&) {}

    void push(const std::string&, const point3d&, const double) {}
    void commit(const int) {}

    template<typename Spatial, typename Temporal>
    double fetch
    (
        const std::string&, const point3d&, const int,
        Spatial&, Temporal&
    )
    {
        return 0.0;
    }
};

} // namespace mui

#endif
