function(perceptshift_set_warnings target)
  if(MSVC)
    target_compile_options(${target} PRIVATE /W4 /permissive-)
  else()
    target_compile_options(${target} PRIVATE
      -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion
      -Wshadow -Wnon-virtual-dtor -Wold-style-cast -Wcast-align
      -Wunused -Woverloaded-virtual -Wnull-dereference
    )
    if(PERCEPTSHIFT_WARNINGS_AS_ERRORS)
      # Project-owned diagnostics as errors. Do not promote libstdc++ / system
      # header false positives (e.g. GCC 13 -Wnull-dereference in <streambuf>).
      target_compile_options(${target} PRIVATE
        -Werror=conversion
        -Werror=sign-conversion
        -Werror=deprecated-declarations
        -Werror=return-type
        -Werror=init-self
        -Werror=uninitialized
      )
    endif()
  endif()
endfunction()
