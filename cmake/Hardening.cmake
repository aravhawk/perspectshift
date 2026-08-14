function(perceptshift_enable_hardening target)
  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(${target} PRIVATE
      -fstack-protector-strong
      -D_FORTIFY_SOURCE=2
    )
    if(NOT APPLE)
      target_link_options(${target} PRIVATE
        -Wl,-z,relro
        -Wl,-z,now
      )
    endif()
  endif()
endfunction()
